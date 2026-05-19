import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import api from '../services/api';
import './ActivateAccount.css';

const STAGES = {
  VALIDATING: 'validating',
  SET_PASSWORD: 'set_password',
  SUCCESS: 'success',
  ERROR: 'error',
  EXPIRED: 'expired'
};

function ActivateAccount() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [stage, setStage] = useState(STAGES.VALIDATING);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [userData, setUserData] = useState(null);

  // Password form
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState(null);

  useEffect(() => {
    if (token) {
      validateToken();
    } else {
      setStage(STAGES.ERROR);
      setError('No activation token provided. Please use the link from your activation email.');
    }
  }, [token]);

  const validateToken = async () => {
    try {
      const response = await api.post('/api/v1/admin/users/activate/validate', {
        token
      });

      if (response.data.success) {
        setUserData(response.data.data);
        setStage(STAGES.SET_PASSWORD);
      } else {
        setStage(STAGES.ERROR);
        setError('Invalid activation token.');
      }
    } catch (err) {
      console.error('Token validation error:', err);
      const errorDetail = err.response?.data?.detail || err.detail || 'Failed to validate token';

      if (errorDetail.includes('expired')) {
        setStage(STAGES.EXPIRED);
      } else {
        setStage(STAGES.ERROR);
        setError(errorDetail);
      }
    }
  };

  const validatePassword = () => {
    setPasswordError(null);

    if (password.length < 8) {
      setPasswordError('Password must be at least 8 characters long');
      return false;
    }

    if (!/[A-Z]/.test(password)) {
      setPasswordError('Password must contain at least one uppercase letter');
      return false;
    }

    if (!/[a-z]/.test(password)) {
      setPasswordError('Password must contain at least one lowercase letter');
      return false;
    }

    if (!/[0-9]/.test(password)) {
      setPasswordError('Password must contain at least one number');
      return false;
    }

    if (password !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return false;
    }

    return true;
  };

  const handleActivate = async (e) => {
    e.preventDefault();

    if (!validatePassword()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/api/v1/admin/users/activate/complete', {
        token,
        password
      });

      if (response.data.success) {
        setStage(STAGES.SUCCESS);
      } else {
        setError('Failed to activate account.');
      }
    } catch (err) {
      console.error('Activation error:', err);
      setError(err.response?.data?.detail || err.detail || 'Failed to activate account. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const getPasswordStrength = () => {
    let strength = 0;
    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/[a-z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^A-Za-z0-9]/.test(password)) strength++;
    return strength;
  };

  const renderValidating = () => (
    <div className="activate-content centered">
      <div className="spinner large"></div>
      <h2>Validating your activation link...</h2>
      <p>Please wait while we verify your account.</p>
    </div>
  );

  const renderSetPassword = () => {
    const strength = getPasswordStrength();
    const strengthLabel = strength <= 2 ? 'Weak' : strength <= 4 ? 'Medium' : 'Strong';
    const strengthClass = strength <= 2 ? 'weak' : strength <= 4 ? 'medium' : 'strong';

    return (
      <div className="activate-content">
        <div className="welcome-header">
          <h2>Welcome, {userData?.first_name}!</h2>
          <p>Set your password to activate your account.</p>
        </div>

        <form onSubmit={handleActivate} className="password-form">
          <div className="form-group">
            <label>New Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
            />
            {password && (
              <div className="password-strength">
                <div className={`strength-bar ${strengthClass}`}>
                  <div className="strength-fill" style={{ width: `${(strength / 6) * 100}%` }}></div>
                </div>
                <span className={`strength-label ${strengthClass}`}>{strengthLabel}</span>
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm your password"
              required
            />
          </div>

          <div className="password-requirements">
            <h4>Password Requirements</h4>
            <ul>
              <li className={password.length >= 8 ? 'met' : ''}>At least 8 characters</li>
              <li className={/[A-Z]/.test(password) ? 'met' : ''}>One uppercase letter</li>
              <li className={/[a-z]/.test(password) ? 'met' : ''}>One lowercase letter</li>
              <li className={/[0-9]/.test(password) ? 'met' : ''}>One number</li>
            </ul>
          </div>

          {(passwordError || error) && (
            <div className="error-message">{passwordError || error}</div>
          )}

          <button type="submit" className="btn-activate" disabled={loading}>
            {loading ? 'Activating...' : 'Activate Account'}
          </button>
        </form>
      </div>
    );
  };

  const renderSuccess = () => (
    <div className="activate-content centered success">
      <div className="success-icon">✓</div>
      <h2>Account Activated!</h2>
      <p>Your account has been successfully activated. You can now log in to Perennia AI.</p>

      <div className="next-steps">
        <h4>What's Next?</h4>
        <ul>
          <li>Log in with your email and new password</li>
          <li>Review your assigned responsibilities</li>
          <li>Check out your personalized KPI scorecard</li>
          <li>Start managing your pipeline</li>
        </ul>
      </div>

      <button className="btn-login" onClick={() => navigate('/login')}>
        Go to Login
      </button>
    </div>
  );

  const renderError = () => (
    <div className="activate-content centered error">
      <div className="error-icon">!</div>
      <h2>Activation Failed</h2>
      <p>{error || 'There was a problem activating your account.'}</p>

      <div className="help-text">
        <p>If you continue to have problems, please contact your administrator for assistance.</p>
      </div>

      <button className="btn-secondary" onClick={() => navigate('/login')}>
        Go to Login
      </button>
    </div>
  );

  const renderExpired = () => (
    <div className="activate-content centered expired">
      <div className="expired-icon">⏰</div>
      <h2>Link Expired</h2>
      <p>Your activation link has expired. Activation links are valid for 7 days.</p>

      <div className="help-text">
        <p>Please contact your administrator to request a new activation email.</p>
      </div>

      <button className="btn-secondary" onClick={() => navigate('/login')}>
        Go to Login
      </button>
    </div>
  );

  const renderCurrentStage = () => {
    switch (stage) {
      case STAGES.VALIDATING:
        return renderValidating();
      case STAGES.SET_PASSWORD:
        return renderSetPassword();
      case STAGES.SUCCESS:
        return renderSuccess();
      case STAGES.EXPIRED:
        return renderExpired();
      case STAGES.ERROR:
      default:
        return renderError();
    }
  };

  return (
    <div className="activate-account-page">
      <div className="activate-container">
        <div className="logo">
          <h1>Perennia AI</h1>
        </div>
        {renderCurrentStage()}
      </div>
    </div>
  );
}

export default ActivateAccount;
