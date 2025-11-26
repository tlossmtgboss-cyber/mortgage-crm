import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../services/api';
import './MortgagePlannerQuestionnaire.css';

function MortgagePlannerQuestionnaire() {
  const [searchParams] = useSearchParams();
  const loId = searchParams.get('lo'); // Loan officer ID from URL

  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState(null);

  const [formData, setFormData] = useState({
    // Personal Info
    name: '',
    email: '',
    phone: '',

    // Home Ownership
    isVeteran: '',
    hasOwnedHomeBefore: '',
    currentHousingStatus: '',
    previousMortgageType: '',
    currentMonthlyPayment: '',

    // Mortgage Preferences
    mortgageImportance: [],

    // Personal Goals
    personalGoals: [],

    // Financial Philosophy
    financialPhilosophy: '',

    // Professional Network
    hasTaxDeferredRetirement: '',
    hasFinancialPlanner: '',
    hasAccountant: '',
    hasLifeInsuranceAgent: '',
    lifeInsuranceAgentRating: '',
    hasEstatePlanner: ''
  });

  const totalSteps = 5;

  const handleInputChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleMultiSelect = (field, value) => {
    setFormData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  const nextStep = () => {
    if (currentStep < totalSteps) {
      setCurrentStep(currentStep + 1);
    }
  };

  const prevStep = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      await axios.post(`${API_BASE_URL}/api/v1/questionnaire/mortgage-planner`, {
        ...formData,
        loan_officer_id: loId,
        source: 'mortgage_planner_questionnaire',
        submitted_at: new Date().toISOString()
      });

      setIsSubmitted(true);
    } catch (err) {
      console.error('Failed to submit questionnaire:', err);
      setError('Failed to submit your questionnaire. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const isStepValid = () => {
    switch (currentStep) {
      case 1:
        return formData.name && formData.email && formData.phone;
      case 2:
        return formData.isVeteran && formData.hasOwnedHomeBefore && formData.currentHousingStatus;
      case 3:
        return formData.mortgageImportance.length > 0;
      case 4:
        return formData.personalGoals.length > 0 && formData.financialPhilosophy;
      case 5:
        return formData.hasTaxDeferredRetirement && formData.hasFinancialPlanner &&
               formData.hasAccountant && formData.hasLifeInsuranceAgent && formData.hasEstatePlanner;
      default:
        return true;
    }
  };

  if (isSubmitted) {
    return (
      <div className="questionnaire-page">
        <div className="questionnaire-container">
          <div className="success-message">
            <div className="success-icon">✓</div>
            <h2>Thank You!</h2>
            <p>Your Mortgage Planning Questionnaire has been submitted successfully.</p>
            <p>A member of The Tim Loss Team will be in touch with you shortly to discuss your mortgage planning needs.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="questionnaire-page">
      <div className="questionnaire-container">
        {/* Header */}
        <div className="questionnaire-header">
          <div className="team-logo">
            <span className="logo-icon">🏠</span>
            <div className="logo-text">
              <span className="team-name">The Tim Loss Team</span>
              <span className="form-title">Mortgage Planner</span>
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="progress-container">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${(currentStep / totalSteps) * 100}%` }}
            />
          </div>
          <div className="progress-text">Step {currentStep} of {totalSteps}</div>
        </div>

        {/* Step Content */}
        <div className="step-content">
          {/* Step 1: Personal Information */}
          {currentStep === 1 && (
            <div className="step">
              <h2>Personal Information</h2>
              <p className="step-description">Let's start with your contact details</p>

              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  placeholder="Enter your full name"
                />
              </div>

              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  placeholder="Enter your email address"
                />
              </div>

              <div className="form-group">
                <label>Phone Number *</label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => handleInputChange('phone', e.target.value)}
                  placeholder="(XXX) XXX-XXXX"
                />
              </div>
            </div>
          )}

          {/* Step 2: Home Ownership History */}
          {currentStep === 2 && (
            <div className="step">
              <h2>Home Ownership History</h2>
              <p className="step-description">Tell us about your housing situation</p>

              <div className="form-group">
                <label>Are you a Veteran? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.isVeteran === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="isVeteran"
                      value="Yes"
                      checked={formData.isVeteran === 'Yes'}
                      onChange={(e) => handleInputChange('isVeteran', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.isVeteran === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="isVeteran"
                      value="No"
                      checked={formData.isVeteran === 'No'}
                      onChange={(e) => handleInputChange('isVeteran', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Have you ever owned a home before? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasOwnedHomeBefore === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasOwnedHomeBefore"
                      value="Yes"
                      checked={formData.hasOwnedHomeBefore === 'Yes'}
                      onChange={(e) => handleInputChange('hasOwnedHomeBefore', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasOwnedHomeBefore === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasOwnedHomeBefore"
                      value="No"
                      checked={formData.hasOwnedHomeBefore === 'No'}
                      onChange={(e) => handleInputChange('hasOwnedHomeBefore', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Do you currently Rent or Own? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.currentHousingStatus === 'Rent' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="currentHousingStatus"
                      value="Rent"
                      checked={formData.currentHousingStatus === 'Rent'}
                      onChange={(e) => handleInputChange('currentHousingStatus', e.target.value)}
                    />
                    <span>Rent</span>
                  </label>
                  <label className={`radio-option ${formData.currentHousingStatus === 'Own' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="currentHousingStatus"
                      value="Own"
                      checked={formData.currentHousingStatus === 'Own'}
                      onChange={(e) => handleInputChange('currentHousingStatus', e.target.value)}
                    />
                    <span>Own</span>
                  </label>
                </div>
              </div>

              {formData.hasOwnedHomeBefore === 'Yes' && (
                <>
                  <div className="form-group">
                    <label>What type of mortgage did you have?</label>
                    <select
                      value={formData.previousMortgageType}
                      onChange={(e) => handleInputChange('previousMortgageType', e.target.value)}
                    >
                      <option value="">Select mortgage type</option>
                      <option value="Conventional">Conventional</option>
                      <option value="FHA">FHA</option>
                      <option value="VA">VA</option>
                      <option value="USDA">USDA</option>
                      <option value="Jumbo">Jumbo</option>
                      <option value="Other">Other</option>
                      <option value="Not Sure">Not Sure</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>How much are you paying monthly for your mortgage payment?</label>
                    <input
                      type="text"
                      value={formData.currentMonthlyPayment}
                      onChange={(e) => handleInputChange('currentMonthlyPayment', e.target.value)}
                      placeholder="e.g., 1500"
                    />
                  </div>
                </>
              )}
            </div>
          )}

          {/* Step 3: Mortgage Priorities */}
          {currentStep === 3 && (
            <div className="step">
              <h2>Mortgage Structure Priorities</h2>
              <p className="step-description">
                There are many ways to structure your mortgage and the associated risks and benefits of certain types of loans.
                Which are most important to you? (Select all that apply)
              </p>

              <div className="form-group">
                <div className="checkbox-grid">
                  {[
                    { value: 'Lowest Payment', description: 'Minimize monthly payments' },
                    { value: 'Lowest Interest Rate', description: 'Get the best rate possible' },
                    { value: 'Fastest Payoff', description: 'Pay off your home quickly' },
                    { value: 'Lowest Total Cost', description: 'Minimize total interest paid' },
                    { value: 'Maximum Flexibility', description: 'Keep options open' },
                    { value: 'Tax Benefits', description: 'Optimize for tax advantages' },
                    { value: 'Build Equity Faster', description: 'Increase home ownership stake' },
                    { value: 'Predictable Payments', description: 'Stable monthly payments' }
                  ].map((option) => (
                    <label
                      key={option.value}
                      className={`checkbox-option ${formData.mortgageImportance.includes(option.value) ? 'selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.mortgageImportance.includes(option.value)}
                        onChange={() => handleMultiSelect('mortgageImportance', option.value)}
                      />
                      <div className="option-content">
                        <span className="option-title">{option.value}</span>
                        <span className="option-description">{option.description}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Personal Goals & Philosophy */}
          {currentStep === 4 && (
            <div className="step">
              <h2>Personal Goals & Financial Philosophy</h2>
              <p className="step-description">Help us understand your financial priorities</p>

              <div className="form-group">
                <label>Which of the following personal goals are most important to you? (Select all that apply) *</label>
                <div className="checkbox-grid">
                  {[
                    { value: 'Building your net worth', description: 'Growing your overall wealth' },
                    { value: 'Moving to a larger home within the next 2 to 5 years', description: 'Upgrading your living space' },
                    { value: 'Achieving financial freedom', description: 'Independence from financial constraints' },
                    { value: 'Paying off debt faster', description: 'Becoming debt-free sooner' },
                    { value: 'Saving for retirement', description: 'Building retirement funds' },
                    { value: 'Saving for childrens education', description: 'College/education funds' },
                    { value: 'Building an investment portfolio', description: 'Growing investments' },
                    { value: 'Starting a business', description: 'Entrepreneurial goals' }
                  ].map((option) => (
                    <label
                      key={option.value}
                      className={`checkbox-option ${formData.personalGoals.includes(option.value) ? 'selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.personalGoals.includes(option.value)}
                        onChange={() => handleMultiSelect('personalGoals', option.value)}
                      />
                      <div className="option-content">
                        <span className="option-title">{option.value}</span>
                        <span className="option-description">{option.description}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="form-group">
                <label>How would you best describe your financial philosophy? *</label>
                <div className="radio-group vertical">
                  {[
                    { value: 'Conservative', description: 'Prefer stability and low risk' },
                    { value: 'Moderate', description: 'Balance between risk and security' },
                    { value: 'Aggressive', description: 'Willing to take calculated risks for higher returns' }
                  ].map((option) => (
                    <label
                      key={option.value}
                      className={`radio-option large ${formData.financialPhilosophy === option.value ? 'selected' : ''}`}
                    >
                      <input
                        type="radio"
                        name="financialPhilosophy"
                        value={option.value}
                        checked={formData.financialPhilosophy === option.value}
                        onChange={(e) => handleInputChange('financialPhilosophy', e.target.value)}
                      />
                      <div className="option-content">
                        <span className="option-title">{option.value}</span>
                        <span className="option-description">{option.description}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 5: Professional Network (Circle of Cashflow) */}
          {currentStep === 5 && (
            <div className="step">
              <h2>Your Professional Network</h2>
              <p className="step-description">
                Help us understand your current financial team so we can provide better recommendations
              </p>

              <div className="form-group">
                <label>Do you participate in a tax-deferred retirement plan at work? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasTaxDeferredRetirement === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasTaxDeferredRetirement"
                      value="Yes"
                      checked={formData.hasTaxDeferredRetirement === 'Yes'}
                      onChange={(e) => handleInputChange('hasTaxDeferredRetirement', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasTaxDeferredRetirement === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasTaxDeferredRetirement"
                      value="No"
                      checked={formData.hasTaxDeferredRetirement === 'No'}
                      onChange={(e) => handleInputChange('hasTaxDeferredRetirement', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Do you work with a Trusted Financial Planner? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasFinancialPlanner === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasFinancialPlanner"
                      value="Yes"
                      checked={formData.hasFinancialPlanner === 'Yes'}
                      onChange={(e) => handleInputChange('hasFinancialPlanner', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasFinancialPlanner === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasFinancialPlanner"
                      value="No"
                      checked={formData.hasFinancialPlanner === 'No'}
                      onChange={(e) => handleInputChange('hasFinancialPlanner', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Do you work with a Trusted Accountant? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasAccountant === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasAccountant"
                      value="Yes"
                      checked={formData.hasAccountant === 'Yes'}
                      onChange={(e) => handleInputChange('hasAccountant', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasAccountant === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasAccountant"
                      value="No"
                      checked={formData.hasAccountant === 'No'}
                      onChange={(e) => handleInputChange('hasAccountant', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Do you work with a Trusted Life Insurance Agent? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasLifeInsuranceAgent === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasLifeInsuranceAgent"
                      value="Yes"
                      checked={formData.hasLifeInsuranceAgent === 'Yes'}
                      onChange={(e) => handleInputChange('hasLifeInsuranceAgent', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasLifeInsuranceAgent === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasLifeInsuranceAgent"
                      value="No"
                      checked={formData.hasLifeInsuranceAgent === 'No'}
                      onChange={(e) => handleInputChange('hasLifeInsuranceAgent', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              {formData.hasLifeInsuranceAgent === 'Yes' && (
                <div className="form-group">
                  <label>How would you rate him/her?</label>
                  <div className="radio-group">
                    {['Excellent', 'Good', 'Fair', 'Poor', 'N/A'].map((rating) => (
                      <label
                        key={rating}
                        className={`radio-option ${formData.lifeInsuranceAgentRating === rating ? 'selected' : ''}`}
                      >
                        <input
                          type="radio"
                          name="lifeInsuranceAgentRating"
                          value={rating}
                          checked={formData.lifeInsuranceAgentRating === rating}
                          onChange={(e) => handleInputChange('lifeInsuranceAgentRating', e.target.value)}
                        />
                        <span>{rating}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="form-group">
                <label>Do you work with a Trusted Estate Planner? *</label>
                <div className="radio-group">
                  <label className={`radio-option ${formData.hasEstatePlanner === 'Yes' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasEstatePlanner"
                      value="Yes"
                      checked={formData.hasEstatePlanner === 'Yes'}
                      onChange={(e) => handleInputChange('hasEstatePlanner', e.target.value)}
                    />
                    <span>Yes</span>
                  </label>
                  <label className={`radio-option ${formData.hasEstatePlanner === 'No' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="hasEstatePlanner"
                      value="No"
                      checked={formData.hasEstatePlanner === 'No'}
                      onChange={(e) => handleInputChange('hasEstatePlanner', e.target.value)}
                    />
                    <span>No</span>
                  </label>
                </div>
              </div>

              <div className="referral-note">
                <div className="note-icon">💡</div>
                <p>
                  Based on your responses, we may be able to connect you with trusted professionals
                  to help complete your financial team. Building a strong circle of advisors is key
                  to achieving your financial goals.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="button-group">
          {currentStep > 1 && (
            <button
              className="btn-prev"
              onClick={prevStep}
              disabled={isSubmitting}
            >
              ← Previous
            </button>
          )}

          {currentStep < totalSteps ? (
            <button
              className="btn-next"
              onClick={nextStep}
              disabled={!isStepValid()}
            >
              Next →
            </button>
          ) : (
            <button
              className="btn-submit"
              onClick={handleSubmit}
              disabled={!isStepValid() || isSubmitting}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Questionnaire'}
            </button>
          )}
        </div>

        {/* Footer */}
        <div className="questionnaire-footer">
          <p>The Tim Loss Team | NMLS# XXXXXX</p>
          <p>Your information is secure and will only be used to help with your mortgage planning.</p>
        </div>
      </div>
    </div>
  );
}

export default MortgagePlannerQuestionnaire;
