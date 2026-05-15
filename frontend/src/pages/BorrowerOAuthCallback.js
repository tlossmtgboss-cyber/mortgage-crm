import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, useParams } from 'react-router-dom';

/**
 * Handles OAuth callbacks for borrower social login.
 *
 * Routes handled:
 * - /apply/oauth/:provider/callback - OAuth provider callbacks
 * - /apply/verify - Email magic link verification
 *
 * On successful auth, redirects to the application with the borrower token.
 */
export default function BorrowerOAuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { provider } = useParams();

  const [status, setStatus] = useState('processing');
  const [error, setError] = useState(null);

  useEffect(() => {
    handleCallback();
  }, []);

  const handleCallback = async () => {
    // Check for token in URL (successful OAuth)
    const token = searchParams.get('token');
    const newUser = searchParams.get('new');
    const loId = searchParams.get('lo_id');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setStatus('error');
      setError(getErrorMessage(errorParam));
      return;
    }

    if (token) {
      // Store the borrower token
      localStorage.setItem('borrower_token', token);

      // Determine redirect destination
      let redirectPath = '/apply/start';

      // If new user, show consent screen first
      if (newUser === '1') {
        redirectPath = '/apply/consent';
      }

      // Add lo_id if present
      if (loId) {
        redirectPath += `?lo_id=${loId}`;
      }

      setStatus('success');

      // Small delay to show success message
      setTimeout(() => {
        navigate(redirectPath, { replace: true });
      }, 1000);
    } else {
      // No token - something went wrong
      setStatus('error');
      setError('Authentication failed. Please try again.');
    }
  };

  const getErrorMessage = (code) => {
    const messages = {
      'token_exchange_failed': 'Failed to complete sign-in. Please try again.',
      'userinfo_failed': 'Failed to retrieve your profile. Please try again.',
      'auth_failed': 'Authentication failed. Please try again.',
      'invalid_link': 'This login link is invalid.',
      'link_expired': 'This login link has expired. Please request a new one.',
      'link_already_used': 'This login link has already been used.',
    };
    return messages[code] || 'An error occurred. Please try again.';
  };

  if (status === 'processing') {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.spinner}></div>
          <h2 style={styles.title}>Completing sign-in...</h2>
          <p style={styles.message}>Please wait while we verify your account.</p>
        </div>
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.successIcon}>✓</div>
          <h2 style={styles.title}>Sign-in successful!</h2>
          <p style={styles.message}>Redirecting to your application...</p>
        </div>
      </div>
    );
  }

  // Error state
  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.errorIcon}>⚠️</div>
        <h2 style={styles.title}>Sign-in Failed</h2>
        <p style={styles.message}>{error}</p>
        <button
          style={styles.button}
          onClick={() => navigate('/apply/login', { replace: true })}
        >
          Try Again
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #f6f9fc 0%, #eef2f7 100%)',
    padding: '20px',
  },
  card: {
    background: 'white',
    borderRadius: '16px',
    boxShadow: '0 4px 24px rgba(0, 0, 0, 0.08)',
    padding: '48px',
    textAlign: 'center',
    maxWidth: '400px',
    width: '100%',
  },
  spinner: {
    width: '48px',
    height: '48px',
    border: '3px solid #e5e7eb',
    borderTopColor: '#1F3D2E',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
    margin: '0 auto 24px',
  },
  successIcon: {
    width: '64px',
    height: '64px',
    background: '#2D7A52',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    fontSize: '32px',
    fontWeight: 'bold',
    margin: '0 auto 24px',
  },
  errorIcon: {
    fontSize: '48px',
    marginBottom: '24px',
  },
  title: {
    fontSize: '20px',
    fontWeight: '600',
    color: '#111827',
    margin: '0 0 12px 0',
  },
  message: {
    fontSize: '14px',
    color: '#6b7280',
    margin: '0 0 24px 0',
  },
  button: {
    padding: '12px 24px',
    background: '#1F3D2E',
    border: 'none',
    borderRadius: '8px',
    color: 'white',
    fontSize: '14px',
    fontWeight: '500',
    cursor: 'pointer',
  },
};

// Add keyframes for spinner animation
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`;
document.head.appendChild(styleSheet);
