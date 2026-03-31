import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import onboardingApi from '../services/onboardingApi';
import { ROLES, PASSWORD_REQUIREMENTS } from '../constants/roles';
import './AcceptInvite.css';

const AcceptInvite = () => {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Also check query param for token (supports both /invite/accept/:token and /accept-invite?token=xxx)
  const inviteToken = token || searchParams.get('token');

  const [validationState, setValidationState] = useState('loading'); // loading, valid, expired, already_accepted, invalid
  const [inviteData, setInviteData] = useState(null);
  const [formData, setFormData] = useState({
    password: '',
    confirmPassword: ''
  });
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (inviteToken) {
      validateToken();
    } else {
      setValidationState('invalid');
    }
  }, [inviteToken]);

  const validateToken = async () => {
    try {
      const response = await onboardingApi.validateInviteToken(inviteToken);
      if (response.valid) {
        setInviteData(response.invite);
        setValidationState('valid');
      } else {
        setValidationState(response.status || 'invalid');
      }
    } catch (error) {
      console.error('Token validation error:', error);
      const code = error.error_code || '';
      const msg = (error.message || '').toLowerCase();
      if (code === 'TOKEN_EXPIRED' || msg.includes('expired')) {
        setValidationState('expired');
      } else if (code === 'TOKEN_USED' || msg.includes('accepted') || msg.includes('used')) {
        setValidationState('already_accepted');
      } else {
        setValidationState('invalid');
      }
    }
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < PASSWORD_REQUIREMENTS.minLength) {
      newErrors.password = `Password must be at least ${PASSWORD_REQUIREMENTS.minLength} characters`;
    } else {
      const checks = [];
      if (PASSWORD_REQUIREMENTS.requireUppercase && !/[A-Z]/.test(formData.password)) checks.push('uppercase letter');
      if (PASSWORD_REQUIREMENTS.requireLowercase && !/[a-z]/.test(formData.password)) checks.push('lowercase letter');
      if (PASSWORD_REQUIREMENTS.requireDigit && !/\d/.test(formData.password)) checks.push('number');
      if (checks.length > 0) {
        newErrors.password = `Password must include: ${checks.join(', ')}`;
      }
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsSubmitting(true);
    try {
      const response = await onboardingApi.acceptInvite(inviteToken, {
        password: formData.password
      });

      // Store auth token if provided
      if (response.access_token) {
        localStorage.setItem('token', response.access_token);
      }

      // Navigate to onboarding wizard
      navigate('/onboarding', {
        state: {
          fromInvite: true,
          userId: response.user_id,
          onboardingId: response.onboarding_id
        }
      });
    } catch (error) {
      console.error('Accept invite error:', error);
      setErrors({ submit: error.message || 'Failed to accept invite. Please try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear error when user starts typing
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: null }));
    }
  };

  // Loading State
  if (validationState === 'loading') {
    return (
      <div className="accept-invite-page">
        <div className="invite-container">
          <div className="loading-state">
            <div className="spinner-large"></div>
            <h2>Validating your invitation...</h2>
            <p>Please wait while we verify your invite link</p>
          </div>
        </div>
      </div>
    );
  }

  // Invalid Token State
  if (validationState === 'invalid') {
    return (
      <div className="accept-invite-page">
        <div className="invite-container">
          <div className="error-state">
            <div className="error-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M15 9l-6 6M9 9l6 6" />
              </svg>
            </div>
            <h2>Invalid Invitation</h2>
            <p>This invitation link is invalid or has been corrupted. Please contact your administrator for a new invite.</p>
            <button className="btn-secondary" onClick={() => navigate('/login')}>
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Expired Token State
  if (validationState === 'expired') {
    return (
      <div className="accept-invite-page">
        <div className="invite-container">
          <div className="error-state expired">
            <div className="error-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <h2>Invitation Expired</h2>
            <p>This invitation has expired. Employee invitations are valid for 7 days. Please contact your administrator for a new invite.</p>
            <button className="btn-secondary" onClick={() => navigate('/login')}>
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Already Accepted State
  if (validationState === 'already_accepted') {
    return (
      <div className="accept-invite-page">
        <div className="invite-container">
          <div className="success-state">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
            <h2>Already Accepted</h2>
            <p>This invitation has already been accepted. If you need to reset your password, please use the forgot password feature.</p>
            <button className="btn-primary" onClick={() => navigate('/login')}>
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Valid Token - Show Accept Form
  return (
    <div className="accept-invite-page">
      <div className="invite-container">
        <div className="invite-header">
          <div className="company-logo">
            <svg viewBox="0 0 40 40" fill="none">
              <rect width="40" height="40" rx="8" fill="#3b82f6"/>
              <path d="M12 28V12h4l4 10 4-10h4v16h-3V17l-3.5 9h-3L15 17v11h-3z" fill="white"/>
            </svg>
          </div>
          <h1>Welcome to Perennia AI</h1>
          <p>You've been invited to join the team</p>
        </div>

        <div className="invite-details">
          <div className="detail-card">
            <div className="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
            <div className="detail-content">
              <span className="detail-label">Name</span>
              <span className="detail-value">{inviteData?.first_name} {inviteData?.last_name}</span>
            </div>
          </div>

          <div className="detail-card">
            <div className="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </div>
            <div className="detail-content">
              <span className="detail-label">Email</span>
              <span className="detail-value">{inviteData?.email}</span>
            </div>
          </div>

          <div className="detail-card">
            <div className="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="8.5" cy="7" r="4" />
                <path d="M20 8v6M23 11h-6" />
              </svg>
            </div>
            <div className="detail-content">
              <span className="detail-label">Role</span>
              <span className={`detail-value role-badge ${ROLES[inviteData?.permission_role]?.className || ''}`}>{ROLES[inviteData?.permission_role]?.label || inviteData?.permission_role}</span>
            </div>
          </div>

          {inviteData?.job_title && (
            <div className="detail-card">
              <div className="detail-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                  <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                </svg>
              </div>
              <div className="detail-content">
                <span className="detail-label">Title</span>
                <span className="detail-value">{inviteData?.job_title}</span>
              </div>
            </div>
          )}
        </div>

        <form className="password-form" onSubmit={handleSubmit}>
          <h3>Set Your Password</h3>
          <p>Create a secure password to complete your account setup</p>

          {errors.submit && (
            <div className="form-error-banner">
              {errors.submit}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="password-input-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                id="password"
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                placeholder="Enter your password"
                className={errors.password ? 'error' : ''}
              />
              <button
                type="button"
                className="toggle-password"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
            {errors.password && <span className="field-error">{errors.password}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              type={showPassword ? 'text' : 'password'}
              id="confirmPassword"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleInputChange}
              placeholder="Confirm your password"
              className={errors.confirmPassword ? 'error' : ''}
            />
            {errors.confirmPassword && <span className="field-error">{errors.confirmPassword}</span>}
          </div>

          <div className="password-requirements">
            <span className="requirements-title">Password must contain:</span>
            <ul>
              <li className={formData.password.length >= PASSWORD_REQUIREMENTS.minLength ? 'met' : ''}>At least {PASSWORD_REQUIREMENTS.minLength} characters</li>
              {PASSWORD_REQUIREMENTS.requireUppercase && <li className={/[A-Z]/.test(formData.password) ? 'met' : ''}>One uppercase letter</li>}
              {PASSWORD_REQUIREMENTS.requireLowercase && <li className={/[a-z]/.test(formData.password) ? 'met' : ''}>One lowercase letter</li>}
              {PASSWORD_REQUIREMENTS.requireDigit && <li className={/\d/.test(formData.password) ? 'met' : ''}>One number</li>}
            </ul>
          </div>

          <button
            type="submit"
            className="btn-submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <div className="btn-spinner"></div>
                Creating Account...
              </>
            ) : (
              <>
                Accept Invitation
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </>
            )}
          </button>
        </form>

        <div className="invite-footer">
          <p>Already have an account? <a href="/login">Sign in</a></p>
        </div>
      </div>
    </div>
  );
};

export default AcceptInvite;
