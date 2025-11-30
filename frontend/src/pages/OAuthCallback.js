import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import './OAuthCallback.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

// Helper to notify parent - uses localStorage as fallback when window.opener is blocked by COOP
const notifyParent = (type, data) => {
  // Store result in localStorage for parent to poll (works even when COOP blocks window.opener)
  const result = { type, ...data, timestamp: Date.now() };
  localStorage.setItem('oauth_result', JSON.stringify(result));

  // Also try postMessage if window.opener is available
  try {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type, ...data }, window.location.origin);
    }
  } catch (e) {
    // COOP policy may block this - that's okay, localStorage fallback will work
    console.log('postMessage blocked by COOP, using localStorage fallback');
  }
};

function OAuthCallback() {
  const location = useLocation();
  const [status, setStatus] = useState('processing'); // processing, success, error
  const [message, setMessage] = useState('Connecting your account...');
  const [provider, setProvider] = useState('');

  useEffect(() => {
    const handleOAuthCallback = async () => {
      const params = new URLSearchParams(location.search);
      const code = params.get('code');
      const state = params.get('state');
      const error = params.get('error');
      const errorDescription = params.get('error_description');

      // Determine provider from state or URL
      const providerName = state?.includes('gmail') ? 'Gmail' : 'Microsoft 365';
      setProvider(providerName);

      const errorType = providerName === 'Gmail' ? 'GMAIL_OAUTH_ERROR' : 'MICROSOFT_OAUTH_ERROR';
      const successType = providerName === 'Gmail' ? 'GMAIL_OAUTH_SUCCESS' : 'MICROSOFT_OAUTH_SUCCESS';

      if (error) {
        setStatus('error');
        const errorMsg = errorDescription || `Failed to connect ${providerName}. Please try again.`;
        setMessage(errorMsg);
        notifyParent(errorType, { error: errorMsg });
        return;
      }

      if (!code) {
        setStatus('error');
        const errorMsg = 'No authorization code received. Please try again.';
        setMessage(errorMsg);
        notifyParent(errorType, { error: errorMsg });
        return;
      }

      try {
        const token = localStorage.getItem('token');

        // Determine the correct endpoint based on provider
        const endpoint = providerName === 'Gmail'
          ? `${API_BASE_URL}/api/v1/gmail/callback`
          : `${API_BASE_URL}/api/v1/microsoft/connect`;

        // Build request body - Microsoft expects authorization_code, Gmail expects code
        const requestBody = providerName === 'Gmail'
          ? { code, redirect_uri: `${window.location.origin}/oauth/callback` }
          : { authorization_code: code, redirect_uri: `${window.location.origin}/oauth/callback` };

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        });

        if (response.ok) {
          setStatus('success');
          setMessage(`${providerName} connected successfully!`);
          notifyParent(successType, { provider: providerName.toLowerCase() });

          // Auto-close after a brief delay to show success message
          setTimeout(() => {
            window.close();
          }, 1500);
        } else {
          const errorData = await response.json();
          setStatus('error');
          const errorMsg = errorData.detail || `Failed to connect ${providerName}. Please try again.`;
          setMessage(errorMsg);
          notifyParent(errorType, { error: errorMsg });
        }
      } catch (err) {
        console.error('OAuth callback error:', err);
        const errorMsg = 'An error occurred while connecting. Please try again.';
        setStatus('error');
        setMessage(errorMsg);
        notifyParent(errorType, { error: err.message || errorMsg });
      }
    };

    handleOAuthCallback();
  }, [location]);

  const handleClose = () => {
    if (window.opener) {
      window.close();
    } else {
      window.location.href = '/settings';
    }
  };

  return (
    <div className="oauth-callback-page">
      <div className="oauth-callback-card">
        {status === 'processing' && (
          <>
            <div className="oauth-spinner"></div>
            <h2>Connecting...</h2>
            <p>{message}</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="oauth-icon success">✓</div>
            <h2>Connected!</h2>
            <p>{message}</p>
            <p className="oauth-hint">You can now close this window.</p>
            <button className="oauth-close-btn" onClick={handleClose}>
              Close Window
            </button>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="oauth-icon error">✕</div>
            <h2>Connection Failed</h2>
            <p>{message}</p>
            <button className="oauth-close-btn" onClick={handleClose}>
              Close Window
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default OAuthCallback;
