import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import './AccountVerification.css';
import { setTokens } from '../utils/tokenStore';

// API base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function AccountVerification() {
  const navigate = useNavigate();
  const location = useLocation();

  // Get user data from navigation state or localStorage
  const userData = location.state || {};
  const [email] = useState(userData.email || '');
  const [userId] = useState(userData.userId || null);

  const [step, setStep] = useState(1); // 1: Email sent, 2: Phone verification, 3: All done
  const [verificationMethod, setVerificationMethod] = useState('text'); // 'text' or 'email'
  const [phoneNumber, setPhoneNumber] = useState(userData.phone || '');
  const [verificationCode, setVerificationCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resendDisabled, setResendDisabled] = useState(false);
  const [resendTimer, setResendTimer] = useState(0);

  // Mask email for display
  const maskEmail = (email) => {
    if (!email) return '';
    const [localPart, domain] = email.split('@');
    if (localPart.length <= 2) return email;
    return `${localPart.substring(0, 2)}${'*'.repeat(Math.min(localPart.length - 2, 4))}@${domain}`;
  };

  // Format phone for display
  const formatPhone = (phone) => {
    if (!phone) return '';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    return phone;
  };

  // Handle resend timer
  useEffect(() => {
    if (resendTimer > 0) {
      const timer = setTimeout(() => setResendTimer(resendTimer - 1), 1000);
      return () => clearTimeout(timer);
    } else {
      setResendDisabled(false);
    }
  }, [resendTimer]);

  // Resend email verification
  const handleResendEmail = async () => {
    setLoading(true);
    setError('');
    try {
      await axios.post(`${API_BASE_URL}/api/v1/verification/resend-email`, {
        email,
        user_id: userId
      });
      setResendDisabled(true);
      setResendTimer(60);
    } catch (err) {
      setError('Failed to resend email. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Check if email is verified and move to step 2
  const handleEmailVerified = async () => {
    // In production, this would check with the backend
    // For now, we'll simulate moving to step 2
    setStep(2);
  };

  // Send phone verification code
  const handleSendPhoneCode = async () => {
    if (!phoneNumber) {
      setError('Please enter a phone number');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await axios.post(`${API_BASE_URL}/api/v1/verification/send-phone-code`, {
        phone: phoneNumber,
        method: verificationMethod,
        user_id: userId
      });
      setResendDisabled(true);
      setResendTimer(60);
    } catch (err) {
      setError('Failed to send verification code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Verify phone code
  const handleVerifyPhoneCode = async () => {
    if (!verificationCode || verificationCode.length < 4) {
      setError('Please enter the verification code');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await axios.post(`${API_BASE_URL}/api/v1/verification/verify-phone`, {
        phone: phoneNumber,
        code: verificationCode,
        user_id: userId
      });
      setStep(3); // Move to "All done" step
    } catch (err) {
      setError('Invalid verification code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Complete verification and go to dashboard
  const handleComplete = async () => {
    // Mark verification as complete
    if (userData.token) {
      await setTokens({ access_token: userData.token });
      await setTokens({ user_data: {
        id: userId,
        email: email,
        full_name: userData.full_name,
        verified: true
      } });
    }
    navigate('/dashboard');
  };

  // Skip phone verification (optional)
  const handleSkipPhone = () => {
    setStep(3);
  };

  return (
    <div className="verification-page">
      <div className="verification-container">
        {/* Step 1: Email Verification Sent */}
        {step === 1 && (
          <div className="verification-step email-step">
            <div className="verification-content">
              <div className="verification-icon">
                <div className="mailbox-icon">
                  <svg viewBox="0 0 100 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="10" y="20" width="60" height="40" rx="4" fill="#4A5568" />
                    <rect x="15" y="25" width="50" height="30" rx="2" fill="#718096" />
                    <path d="M70 30 L85 40 L70 50" fill="#4A5568" />
                    <rect x="70" y="35" width="20" height="10" fill="#E53E3E" />
                    <path d="M25 35 L50 50 L75 35" stroke="#A0AEC0" strokeWidth="2" fill="none" />
                    <rect x="55" y="28" width="10" height="6" fill="#ECC94B" transform="rotate(-15 55 28)" />
                  </svg>
                </div>
              </div>

              <h1>You've got email!</h1>
              <p className="verification-message">
                We sent an email to <strong>{maskEmail(email)}</strong>. Simply
                follow the link in the email to finish setting up
                your new account.
              </p>

              <div className="verification-actions">
                <button
                  className="btn-resend"
                  onClick={handleResendEmail}
                  disabled={loading || resendDisabled}
                >
                  {resendDisabled
                    ? `Resend in ${resendTimer}s`
                    : 'Resend Email'
                  }
                </button>
              </div>

              {/* For demo purposes - remove in production */}
              <div className="demo-skip">
                <button
                  className="btn-skip-demo"
                  onClick={handleEmailVerified}
                >
                  I've verified my email
                </button>
              </div>

              {error && <div className="error-message">{error}</div>}
            </div>
          </div>
        )}

        {/* Step 2: Phone Verification Setup */}
        {step === 2 && (
          <div className="verification-step phone-step">
            <div className="verification-header">
              <span className="step-label">Set Up 2-Step Verification</span>
            </div>

            <div className="verification-content">
              <h1>You've successfully created your account! Next, add extra security.</h1>

              <div className="security-notice">
                <span className="notice-icon">!</span>
                <p>
                  We want to make sure your account is secure by protecting it with 2-step verification.
                  You need to set it up before accessing your account.
                </p>
              </div>

              <div className="verification-info">
                <h3>How does 2-Step Verification Work?</h3>
                <p>
                  Once it's set up, you'll enter your user ID and password, and then we'll send you a one-time code.
                  Simply use the code to verify your identity while logging in. If you're logging in on a personal device,
                  you'll have the option to skip entering the code by using biometric or remembering the device.
                </p>
                <p className="info-note">
                  This additional layer of security helps us verify it's you when you log in to your account, and it's required.
                </p>
              </div>

              <div className="phone-verification-form">
                <h3>Send Your Verification Code</h3>
                <p className="form-label">How would you like to receive the code?</p>

                <div className="verification-method-options">
                  <button
                    className={`method-btn ${verificationMethod === 'text' ? 'active' : ''}`}
                    onClick={() => setVerificationMethod('text')}
                  >
                    <span className="method-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="5" y="2" width="14" height="20" rx="2" />
                        <line x1="9" y1="18" x2="15" y2="18" />
                      </svg>
                    </span>
                    Text Me
                  </button>
                  <button
                    className={`method-btn ${verificationMethod === 'email' ? 'active' : ''}`}
                    onClick={() => setVerificationMethod('email')}
                  >
                    <span className="method-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="2" y="4" width="20" height="16" rx="2" />
                        <path d="M2 6 L12 13 L22 6" />
                      </svg>
                    </span>
                    Email Me
                  </button>
                </div>

                <div className="phone-input-section">
                  <label>What phone number would you like us to send the code to?</label>
                  <p className="input-note">
                    We'll send your verification code to this phone number each time you log in.
                    This doesn't have to be the same phone number listed on your policy.
                    This is just the number you wish to receive your code at when you log in.
                    Message and data rates may apply.
                  </p>

                  <div className="phone-input-group">
                    <label>Phone number</label>
                    <input
                      type="tel"
                      value={phoneNumber}
                      onChange={(e) => setPhoneNumber(e.target.value)}
                      placeholder="(___) ___-____"
                      className="phone-input"
                    />
                  </div>
                </div>

                {error && <div className="error-message">{error}</div>}

                <div className="form-actions">
                  <button
                    className="btn-primary"
                    onClick={handleSendPhoneCode}
                    disabled={loading || !phoneNumber}
                  >
                    {loading ? 'Sending...' : 'Continue'}
                  </button>
                  <button
                    className="btn-cancel"
                    onClick={handleSkipPhone}
                  >
                    Cancel
                  </button>
                </div>
              </div>

              {/* Code entry section (shown after sending) */}
              {resendDisabled && (
                <div className="code-entry-section">
                  <h3>Enter Verification Code</h3>
                  <p>We sent a code to {formatPhone(phoneNumber)}</p>
                  <input
                    type="text"
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="Enter code"
                    className="code-input"
                    maxLength={6}
                  />
                  <button
                    className="btn-verify"
                    onClick={handleVerifyPhoneCode}
                    disabled={loading || verificationCode.length < 4}
                  >
                    {loading ? 'Verifying...' : 'Verify Code'}
                  </button>
                  <button
                    className="btn-resend-code"
                    onClick={handleSendPhoneCode}
                    disabled={resendTimer > 0}
                  >
                    {resendTimer > 0 ? `Resend in ${resendTimer}s` : 'Resend Code'}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 3: All Done */}
        {step === 3 && (
          <div className="verification-step complete-step">
            <div className="verification-header">
              <span className="step-label">Set Up 2-Step Verification</span>
            </div>

            <div className="verification-content">
              <h1>You're all set!</h1>

              <div className="success-section">
                <h2>All done</h2>
                <p>
                  You've successfully set up 2-step verification. Remember, you can update 2-step verification anytime.
                  You can also save up to three different contact methods. Just head over to Account Preferences.
                </p>
              </div>

              <div className="next-steps-section">
                <h3>What's next</h3>
                <p>
                  When you log in to your account, you'll enter your user ID and password, and then we'll send a verification code to{' '}
                  <strong>{formatPhone(phoneNumber) || maskEmail(email)}</strong>.
                  Enter the code to let us know it's you and access your account.
                </p>
              </div>

              <div className="complete-actions">
                <button
                  className="btn-continue"
                  onClick={handleComplete}
                >
                  Continue
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AccountVerification;
