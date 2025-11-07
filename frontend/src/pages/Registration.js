import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import './Registration.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function Registration() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedPlan = searchParams.get('plan') || 'professional';

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    company_name: '',
    phone: '',
    plan: selectedPlan
  });

  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState(1); // 1: Account Info, 2: Company Info, 3: Payment

  useEffect(() => {
    loadPlans();
  }, []);

  const loadPlans = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/plans`);
      setPlans(response.data.plans);
    } catch (error) {
      console.error('Failed to load plans:', error);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    setError('');
  };

  const validateStep1 = () => {
    if (!formData.email || !formData.password || !formData.confirmPassword || !formData.full_name) {
      setError('Please fill in all required fields');
      return false;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      setError('Please enter a valid email address');
      return false;
    }

    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters long');
      return false;
    }

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return false;
    }

    return true;
  };

  const validateStep2 = () => {
    if (!formData.company_name) {
      setError('Company name is required');
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (step === 1 && validateStep1()) {
      setStep(2);
    } else if (step === 2 && validateStep2()) {
      setStep(3);
    }
  };

  const handleBack = () => {
    setStep(prev => prev - 1);
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateStep1() || !validateStep2()) {
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await axios.post(`${API_BASE_URL}/api/v1/register`, {
        email: formData.email,
        password: formData.password,
        full_name: formData.full_name,
        company_name: formData.company_name,
        phone: formData.phone,
        plan: formData.plan
      });

      // Check if dev mode (bypass email verification)
      if (response.data.dev_mode && response.data.redirect_to) {
        // Dev mode - create mock session and redirect
        const mockToken = 'dev_token_' + response.data.user_id;
        const mockUser = {
          id: response.data.user_id,
          email: response.data.email,
          full_name: formData.full_name
        };

        localStorage.setItem('token', mockToken);
        localStorage.setItem('user', JSON.stringify(mockUser));

        // Redirect to onboarding or dashboard
        navigate(response.data.redirect_to === '/dashboard' ? '/onboarding' : response.data.redirect_to);
      } else {
        // Production mode - redirect to email verification page
        navigate('/verify-email-sent', {
          state: {
            email: formData.email,
            message: response.data.message
          }
        });
      }

    } catch (error) {
      console.error('Registration failed:', error);
      setError(error.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const selectedPlanInfo = plans.find(p => p.key === formData.plan) || {
    name: 'Professional',
    price_monthly: 199,
    features: []
  };

  return (
    <div className="registration-page">
      <div className="registration-container">
        {/* Left side - Form */}
        <div className="registration-form-section">
          <div className="registration-header">
            <h1>Create Your Account</h1>
            <p>Start your 14-day free trial today</p>
          </div>

          {/* Progress indicator */}
          <div className="progress-steps">
            <div className={`progress-step ${step >= 1 ? 'active' : ''}`}>
              <div className="step-number">{step > 1 ? '✓' : '1'}</div>
              <div className="step-label">Account</div>
            </div>
            <div className="progress-line"></div>
            <div className={`progress-step ${step >= 2 ? 'active' : ''}`}>
              <div className="step-number">{step > 2 ? '✓' : '2'}</div>
              <div className="step-label">Company</div>
            </div>
            <div className="progress-line"></div>
            <div className={`progress-step ${step >= 3 ? 'active' : ''}`}>
              <div className="step-number">3</div>
              <div className="step-label">Confirm</div>
            </div>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="registration-form">
            {/* Step 1: Account Information */}
            {step === 1 && (
              <div className="form-step">
                <div className="form-group">
                  <label>Full Name *</label>
                  <input
                    type="text"
                    name="full_name"
                    value={formData.full_name}
                    onChange={handleInputChange}
                    placeholder="John Smith"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Email Address *</label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    placeholder="john@company.com"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Password *</label>
                  <input
                    type="password"
                    name="password"
                    value={formData.password}
                    onChange={handleInputChange}
                    placeholder="Minimum 8 characters"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Confirm Password *</label>
                  <input
                    type="password"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleInputChange}
                    placeholder="Re-enter your password"
                    required
                  />
                </div>

                <button
                  type="button"
                  className="btn-next"
                  onClick={handleNext}
                >
                  Continue
                </button>
              </div>
            )}

            {/* Step 2: Company Information */}
            {step === 2 && (
              <div className="form-step">
                <div className="form-group">
                  <label>Company Name *</label>
                  <input
                    type="text"
                    name="company_name"
                    value={formData.company_name}
                    onChange={handleInputChange}
                    placeholder="ABC Mortgage Company"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Phone Number</label>
                  <input
                    type="tel"
                    name="phone"
                    value={formData.phone}
                    onChange={handleInputChange}
                    placeholder="(555) 123-4567"
                  />
                </div>

                <div className="form-group">
                  <label>Select Plan *</label>
                  <select
                    name="plan"
                    value={formData.plan}
                    onChange={handleInputChange}
                    required
                  >
                    {plans.map(plan => (
                      <option key={plan.key} value={plan.key}>
                        {plan.name} - ${plan.price_monthly}/month
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-buttons">
                  <button
                    type="button"
                    className="btn-back"
                    onClick={handleBack}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    className="btn-next"
                    onClick={handleNext}
                  >
                    Continue
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Confirmation */}
            {step === 3 && (
              <div className="form-step">
                <div className="confirmation-summary">
                  <h3>Review Your Information</h3>

                  <div className="summary-section">
                    <h4>Account</h4>
                    <p><strong>Name:</strong> {formData.full_name}</p>
                    <p><strong>Email:</strong> {formData.email}</p>
                  </div>

                  <div className="summary-section">
                    <h4>Company</h4>
                    <p><strong>Company:</strong> {formData.company_name}</p>
                    {formData.phone && <p><strong>Phone:</strong> {formData.phone}</p>}
                  </div>

                  <div className="summary-section">
                    <h4>Subscription</h4>
                    <p><strong>Plan:</strong> {selectedPlanInfo.name}</p>
                    <p><strong>Price:</strong> ${selectedPlanInfo.price_monthly}/month</p>
                    <p className="trial-note">14-day free trial included</p>
                  </div>

                  <div className="terms-notice">
                    <p>
                      By creating an account, you agree to our Terms of Service and Privacy Policy.
                      You can cancel anytime during your trial period at no charge.
                    </p>
                  </div>
                </div>

                <div className="form-buttons">
                  <button
                    type="button"
                    className="btn-back"
                    onClick={handleBack}
                  >
                    Back
                  </button>
                  <button
                    type="submit"
                    className="btn-submit"
                    disabled={loading}
                  >
                    {loading ? 'Creating Account...' : 'Create Account'}
                  </button>
                </div>
              </div>
            )}
          </form>

          <div className="registration-footer">
            <p>
              Already have an account?{' '}
              <a href="/login" className="login-link">Sign In</a>
            </p>
          </div>
        </div>

        {/* Right side - Plan Summary */}
        <div className="registration-summary-section">
          <div className="plan-summary-card">
            <h3>Your Selected Plan</h3>

            <div className="plan-details">
              <h2>{selectedPlanInfo.name}</h2>
              <div className="plan-price">
                <span className="price-amount">${selectedPlanInfo.price_monthly}</span>
                <span className="price-period">/month</span>
              </div>

              <div className="trial-badge">
                14-Day Free Trial
              </div>

              <ul className="plan-features-list">
                {selectedPlanInfo.features?.map((feature, index) => (
                  <li key={index}>
                    <span className="check-icon">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
            </div>

            <div className="billing-info">
              <p><strong>What happens next:</strong></p>
              <ol>
                <li>Verify your email address</li>
                <li>Complete onboarding wizard</li>
                <li>Start your 14-day free trial</li>
                <li>You'll be charged after trial ends</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Registration;
