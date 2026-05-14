import React from 'react';
import { toast } from '../../utils/toast';

/**
 * Account creation/login stage - shared between Purchase and Refinance.
 * Provides social OAuth login (Google, Facebook, LinkedIn, Apple) and email magic link.
 */
const AccountStage = ({
  API_URL,
  userAccount,
  setUserAccount,
  emailSending,
  setEmailSending,
  emailSent,
  setEmailSent,
  setCurrentStage,
  isDemoMode,
  navigate,
}) => {
  const handleSocialLogin = (provider) => {
    const providerLower = provider.toLowerCase();
    const returnUrl = encodeURIComponent(window.location.href);
    window.location.href = `${API_URL}/api/v1/borrower-auth/${providerLower}/connect?return_url=${returnUrl}`;
  };

  const handleEmailContinue = async () => {
    if (!userAccount.email || !userAccount.email.includes('@')) {
      toast.error('Please enter a valid email address');
      return;
    }

    setEmailSending(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/borrower-auth/email/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: userAccount.email,
          first_name: userAccount.firstName || '',
          last_name: userAccount.lastName || ''
        })
      });

      if (response.ok) {
        setEmailSent(true);
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to send login link. Please try again.');
      }
    } catch (error) {
      console.error('Email login error:', error);
      toast.error('Failed to send login link. Please try again.');
    } finally {
      setEmailSending(false);
    }
  };

  const socialButtonStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    padding: '12px 16px',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    background: 'white',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 500,
    color: '#374151',
    transition: 'all 0.2s'
  };

  return (
    <div className="stage-content account-creation-stage">
      <div className="stage-header" style={{ textAlign: 'center', marginBottom: '32px' }}>
        <h2>Let's Get Started</h2>
        <p>Create an account to save your progress and come back anytime</p>
      </div>

      <div className="form-card" style={{ maxWidth: '480px', margin: '0 auto' }}>
        {/* Social Login Options */}
        <div className="social-login-section" style={{ marginBottom: '24px' }}>
          <p style={{ textAlign: 'center', color: '#6b7280', marginBottom: '16px', fontSize: '14px' }}>
            Sign up with
          </p>
          <div className="social-buttons" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px',
            marginBottom: '16px'
          }}>
            <button onClick={() => handleSocialLogin('Google')} style={socialButtonStyle}>
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Google
            </button>
            <button onClick={() => handleSocialLogin('Facebook')} style={socialButtonStyle}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="#1877F2">
                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
              Facebook
            </button>
            <button onClick={() => handleSocialLogin('LinkedIn')} style={socialButtonStyle}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="#0A66C2">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
              LinkedIn
            </button>
            <button onClick={() => handleSocialLogin('Apple')} style={socialButtonStyle}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="#000000">
                <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
              </svg>
              Apple
            </button>
          </div>

          <div className="divider" style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            margin: '24px 0'
          }}>
            <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }}></div>
            <span style={{ color: '#9ca3af', fontSize: '14px' }}>or continue with email</span>
            <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }}></div>
          </div>
        </div>

        {/* Email Input */}
        <div className="email-section">
          {emailSent ? (
            <div style={{
              textAlign: 'center',
              padding: '24px',
              background: '#f0fdf4',
              borderRadius: '12px',
              border: '1px solid #bbf7d0'
            }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>&#9993;&#65039;</div>
              <h3 style={{ margin: '0 0 8px', color: '#166534', fontSize: '18px' }}>Check Your Email</h3>
              <p style={{ margin: '0 0 16px', color: '#15803d', fontSize: '14px' }}>
                We sent a login link to <strong>{userAccount.email}</strong>
              </p>
              <p style={{ margin: 0, color: '#6b7280', fontSize: '13px' }}>
                Click the link in the email to continue your application.
              </p>
              <button
                onClick={() => setEmailSent(false)}
                style={{
                  marginTop: '16px',
                  background: 'transparent',
                  border: 'none',
                  color: '#0ea5e9',
                  cursor: 'pointer',
                  fontSize: '14px',
                  textDecoration: 'underline'
                }}
              >
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>Email Address</label>
                <input
                  type="email"
                  value={userAccount.email}
                  onChange={(e) => setUserAccount(prev => ({ ...prev, email: e.target.value }))}
                  placeholder="you@example.com"
                  className="fun-input"
                  style={{ width: '100%' }}
                  disabled={emailSending}
                />
              </div>
              <button
                onClick={handleEmailContinue}
                className="btn-continue"
                style={{ width: '100%', marginBottom: '12px' }}
                disabled={emailSending || !userAccount.email?.includes('@')}
              >
                {emailSending ? 'Sending...' : 'Continue with Email'}
              </button>
            </>
          )}
        </div>

        {/* Login Option for Existing Users */}
        <div style={{
          textAlign: 'center',
          marginTop: '20px',
          padding: '16px',
          background: '#f0f9ff',
          borderRadius: '8px',
          border: '1px solid #bae6fd'
        }}>
          <p style={{ margin: '0 0 12px', color: '#0369a1', fontSize: '14px', fontWeight: 500 }}>
            Already started an application?
          </p>
          <button
            onClick={() => navigate('/apply/login')}
            style={{
              background: '#0ea5e9',
              color: 'white',
              border: 'none',
              padding: '10px 24px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => e.target.style.background = '#0284c7'}
            onMouseOut={(e) => e.target.style.background = '#0ea5e9'}
          >
            Log In to Continue
          </button>
        </div>

        {/* Benefits */}
        <div className="account-benefits" style={{
          marginTop: '24px',
          padding: '16px',
          background: '#f9fafb',
          borderRadius: '8px'
        }}>
          <p style={{ fontWeight: 600, fontSize: '14px', marginBottom: '12px', color: '#374151' }}>
            Why create an account?
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', color: '#6b7280', fontSize: '13px', lineHeight: '1.8' }}>
            <li>Save your progress and return anytime</li>
            <li>Get a personalized experience</li>
            <li>Track your application status</li>
            <li>Receive updates from your loan officer</li>
          </ul>
        </div>

        {/* Demo Mode Button */}
        {isDemoMode && (
          <div style={{ marginTop: '24px', textAlign: 'center' }}>
            <button
              onClick={() => setCurrentStage('declarations')}
              style={{
                padding: '12px 32px',
                background: '#6366f1',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '16px',
                fontWeight: '600',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
            >
              Continue in Demo Mode
            </button>
            <p style={{ marginTop: '8px', fontSize: '12px', color: '#9ca3af' }}>
              Skip account creation for testing purposes
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default AccountStage;
