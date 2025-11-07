import { useLocation, useNavigate } from 'react-router-dom';
import './EmailVerificationSent.css';

function EmailVerificationSent() {
  const location = useLocation();
  const navigate = useNavigate();
  const email = location.state?.email || '';

  return (
    <div className="verification-sent-page">
      <div className="verification-card">
        <div className="success-icon">✉️</div>
        <h1>Check Your Email</h1>
        <p className="main-message">
          We've sent a verification link to <strong>{email}</strong>
        </p>
        <p className="instructions">
          Click the link in the email to verify your account and complete your registration.
        </p>

        <div className="info-box">
          <h3>What's Next?</h3>
          <ol>
            <li>Check your email inbox (and spam folder)</li>
            <li>Click the verification link</li>
            <li>Complete the onboarding wizard</li>
            <li>Start your 14-day free trial</li>
          </ol>
        </div>

        <div className="help-section">
          <p>Didn't receive the email?</p>
          <button className="btn-resend">Resend Verification Email</button>
        </div>

        <button className="btn-back-home" onClick={() => navigate('/')}>
          Back to Home
        </button>
      </div>
    </div>
  );
}

export default EmailVerificationSent;
