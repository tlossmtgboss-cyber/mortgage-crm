import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import './BorrowerLogin.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function BorrowerLogin() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [emailSent, setEmailSent] = useState(false);
  const [showEmailForm, setShowEmailForm] = useState(false);

  // Check for error in URL params
  useEffect(() => {
    const errorParam = searchParams.get('error');
    if (errorParam) {
      setError(getErrorMessage(errorParam));
    }
  }, [searchParams]);

  const getErrorMessage = (code) => {
    const messages = {
      'token_exchange_failed': 'Failed to complete sign-in. Please try again.',
      'userinfo_failed': 'Failed to retrieve your profile. Please try again.',
      'auth_failed': 'Authentication failed. Please try again.',
      'invalid_link': 'This login link is invalid.',
      'link_expired': 'This login link has expired. Please request a new one.',
      'link_already_used': 'This login link has already been used.',
      'apple_not_configured': 'Apple Sign In is not available at this time. Please use Google or Email.',
      'facebook_not_configured': 'Facebook login is not available at this time. Please use Google or Email.',
      'linkedin_not_configured': 'LinkedIn login is not available at this time. Please use Google or Email.',
      'provider_not_configured': 'This login method is not available. Please use Google or Email.',
    };
    return messages[code] || 'An error occurred. Please try again.';
  };

  // Get redirect URL for after login
  const getRedirectUrl = () => {
    const redirect = searchParams.get('redirect') || '/apply/start';
    const loId = searchParams.get('lo_id');
    return { redirect, loId };
  };

  // Initiate social login
  const handleSocialLogin = async (provider) => {
    setLoading(true);
    setError(null);

    try {
      const { redirect, loId } = getRedirectUrl();
      let url = `${API_BASE_URL}/api/v1/borrower-auth/${provider}/connect?redirect_to=${encodeURIComponent(redirect)}`;
      if (loId) {
        url += `&lo_id=${encodeURIComponent(loId)}`;
      }

      const response = await fetch(url);
      const data = await response.json();

      if (data.auth_url) {
        // Redirect to OAuth provider
        window.location.href = data.auth_url;
      } else if (response.status === 500 || data.detail?.includes('not configured')) {
        // Provider not configured
        setError(getErrorMessage(`${provider}_not_configured`));
        setLoading(false);
      } else {
        setError(data.detail || 'Failed to initiate sign-in. Please try again.');
        setLoading(false);
      }
    } catch (err) {
      console.error('Social login error:', err);
      setError('Failed to connect. Please try again.');
      setLoading(false);
    }
  };

  // Handle email login request
  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/borrower-auth/email/request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          first_name: firstName || null,
          last_name: lastName || null,
        }),
      });

      const data = await response.json();

      if (data.success) {
        setEmailSent(true);
      } else {
        setError(data.detail || 'Failed to send login link.');
      }
    } catch (err) {
      console.error('Email login error:', err);
      setError('Failed to send login link. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (emailSent) {
    return (
      <div className="borrower-login">
        <div className="login-container">
          <div className="login-card">
            <div className="email-sent-icon">📧</div>
            <h1>Check Your Email</h1>
            <p className="email-sent-message">
              We've sent a secure login link to <strong>{email}</strong>
            </p>
            <p className="email-sent-help">
              Click the link in your email to continue with your application.
              The link will expire in 24 hours.
            </p>
            <button
              className="btn-secondary"
              onClick={() => {
                setEmailSent(false);
                setEmail('');
              }}
            >
              Use a different email
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="borrower-login">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <h1>Start Your Mortgage Application</h1>
            <p>Sign in to begin or continue your application</p>
          </div>

          {error && (
            <div className="error-alert">
              <span className="error-icon">⚠️</span>
              {error}
            </div>
          )}

          {/* Social Login Buttons */}
          <div className="social-buttons">
            <button
              className="social-btn google-btn"
              onClick={() => handleSocialLogin('google')}
              disabled={loading}
            >
              <svg viewBox="0 0 24 24" className="social-icon">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continue with Google
            </button>

            <button
              className="social-btn apple-btn"
              onClick={() => handleSocialLogin('apple')}
              disabled={loading}
            >
              <svg viewBox="0 0 24 24" className="social-icon">
                <path fill="currentColor" d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
              </svg>
              Continue with Apple
            </button>

            <button
              className="social-btn facebook-btn"
              onClick={() => handleSocialLogin('facebook')}
              disabled={loading}
            >
              <svg viewBox="0 0 24 24" className="social-icon">
                <path fill="#1877F2" d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
              Continue with Facebook
            </button>

            <button
              className="social-btn linkedin-btn"
              onClick={() => handleSocialLogin('linkedin')}
              disabled={loading}
            >
              <svg viewBox="0 0 24 24" className="social-icon">
                <path fill="#0A66C2" d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
              Continue with LinkedIn
            </button>
          </div>

          <div className="divider">
            <span>or</span>
          </div>

          {/* Email Login */}
          {!showEmailForm ? (
            <button
              className="btn-email-option"
              onClick={() => setShowEmailForm(true)}
            >
              Continue with Email
            </button>
          ) : (
            <form onSubmit={handleEmailLogin} className="email-form">
              <div className="form-group">
                <label htmlFor="email">Email Address</label>
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  disabled={loading}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="firstName">First Name (optional)</label>
                  <input
                    type="text"
                    id="firstName"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                    disabled={loading}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="lastName">Last Name (optional)</label>
                  <input
                    type="text"
                    id="lastName"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                    disabled={loading}
                  />
                </div>
              </div>

              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? 'Sending...' : 'Send Login Link'}
              </button>

              <button
                type="button"
                className="btn-back"
                onClick={() => setShowEmailForm(false)}
              >
                Back to sign-in options
              </button>
            </form>
          )}

          <div className="login-footer">
            <p className="consent-notice">
              By continuing, you agree to receive communications about your loan application.
            </p>
            <p className="privacy-notice">
              Your information is protected and will only be used to process your application.
            </p>
          </div>
        </div>

        <div className="login-benefits">
          <h2>Why create an account?</h2>
          <ul>
            <li>
              <span className="benefit-icon">💾</span>
              <div>
                <strong>Save your progress</strong>
                <p>Continue your application anytime</p>
              </div>
            </li>
            <li>
              <span className="benefit-icon">⚡</span>
              <div>
                <strong>Faster completion</strong>
                <p>Auto-fill from your profile</p>
              </div>
            </li>
            <li>
              <span className="benefit-icon">🔒</span>
              <div>
                <strong>Secure access</strong>
                <p>Your data is encrypted and protected</p>
              </div>
            </li>
            <li>
              <span className="benefit-icon">📱</span>
              <div>
                <strong>Access anywhere</strong>
                <p>Complete on any device</p>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
