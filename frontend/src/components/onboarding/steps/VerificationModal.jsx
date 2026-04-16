import React, { useState, useEffect } from 'react';
import './VerificationModal.css';
import { toast } from '../../../utils/toast';
import { getToken } from '../../../utils/tokenStore';

const VerificationModal = ({ type, contact, onClose, onVerified }) => {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(600); // 10 minutes in seconds
  const [canResend, setCanResend] = useState(false);

  useEffect(() => {
    // Countdown timer
    const timer = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          setCanResend(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const formatTime = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const handleCodeChange = (value) => {
    // Only allow digits
    const cleaned = value.replace(/\D/g, '');
    if (cleaned.length <= 6) {
      setCode(cleaned);
      setError('');
    }
  };

  const handleVerify = async () => {
    if (code.length !== 6) {
      setError('Please enter a 6-digit code');
      return;
    }

    setIsVerifying(true);
    setError('');

    try {
      const token = getToken();
      const endpoint = type === 'email'
        ? '/api/v1/onboarding/step-1/verify-email'
        : '/api/v1/onboarding/step-1/verify-sms';

      const response = await fetch(`https://api.perenniaai.com${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ code })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.verified) {
          onVerified();
        } else {
          setError('Invalid or expired code');
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Verification failed');
      }
    } catch (error) {
      console.error('Verification error:', error);
      setError('An error occurred. Please try again.');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleResend = async () => {
    try {
      const token = getToken();
      const endpoint = type === 'email'
        ? '/api/v1/onboarding/step-1/send-email-verification'
        : '/api/v1/onboarding/step-1/send-sms-verification';

      const body = type === 'email'
        ? { email: contact }
        : { phone: contact };

      const response = await fetch(`https://api.perenniaai.com${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      if (response.ok) {
        setTimeRemaining(600);
        setCanResend(false);
        setCode('');
        setError('');
        toast.success('A new verification code has been sent.');
      } else {
        const errorData = await response.json();
        toast.error(errorData.detail || 'Failed to resend code');
      }
    } catch (error) {
      console.error('Resend error:', error);
      toast.error('Failed to resend code. Please try again.');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && code.length === 6) {
      handleVerify();
    }
  };

  return (
    <div className="verification-modal-overlay" onClick={onClose}>
      <div className="verification-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          ×
        </button>

        <div className="modal-header">
          <h2>Verify Your {type === 'email' ? 'Email' : 'Phone Number'}</h2>
          <p>
            We sent a 6-digit code to <strong>{contact}</strong>
          </p>
        </div>

        <div className="modal-body">
          <div className="code-input-container">
            <label htmlFor="verification-code">Enter Verification Code</label>
            <input
              id="verification-code"
              type="text"
              value={code}
              onChange={(e) => handleCodeChange(e.target.value)}
              onKeyPress={handleKeyPress}
              className={`code-input ${error ? 'error' : ''}`}
              placeholder="000000"
              maxLength="6"
              autoFocus
            />
            {error && <span className="error-message">{error}</span>}
          </div>

          <div className="timer-container">
            {timeRemaining > 0 ? (
              <p className="timer">
                Code expires in <strong>{formatTime(timeRemaining)}</strong>
              </p>
            ) : (
              <p className="timer expired">
                Code expired. Please request a new one.
              </p>
            )}
          </div>

          <button
            type="button"
            className="btn-verify"
            onClick={handleVerify}
            disabled={isVerifying || code.length !== 6 || timeRemaining === 0}
          >
            {isVerifying ? 'Verifying...' : 'Verify'}
          </button>

          <div className="resend-container">
            {canResend || timeRemaining === 0 ? (
              <button
                type="button"
                className="btn-resend"
                onClick={handleResend}
              >
                Resend Code
              </button>
            ) : (
              <p className="resend-info">
                Didn't receive a code? You can request a new one after the timer expires.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default VerificationModal;
