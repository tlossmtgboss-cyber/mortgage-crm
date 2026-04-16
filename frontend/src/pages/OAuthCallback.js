import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import './OAuthCallback.css';
import { getToken } from '../utils/tokenStore';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

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
      // Calendly state format: "user_id:random_string"
      // Gmail state includes 'gmail', Microsoft is the default
      let providerName = 'Microsoft 365';
      if (state?.includes('gmail')) {
        providerName = 'Gmail';
      } else if (state?.match(/^\d+:/)) {
        // Calendly state starts with user_id followed by colon
        providerName = 'Calendly';
      }
      setProvider(providerName);

      const errorType = providerName === 'Gmail' ? 'GMAIL_OAUTH_ERROR' :
                        providerName === 'Calendly' ? 'CALENDLY_OAUTH_ERROR' : 'MICROSOFT_OAUTH_ERROR';
      const successType = providerName === 'Gmail' ? 'GMAIL_OAUTH_SUCCESS' :
                          providerName === 'Calendly' ? 'CALENDLY_OAUTH_SUCCESS' : 'MICROSOFT_OAUTH_SUCCESS';

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
        const token = getToken();

        // Determine the correct endpoint based on provider
        let endpoint;
        let requestBody;

        if (providerName === 'Gmail') {
          endpoint = `${API_BASE_URL}/api/v1/gmail/callback`;
          requestBody = { code, redirect_uri: `${window.location.origin}/oauth/callback` };
        } else if (providerName === 'Calendly') {
          // Calendly uses GET request with query params
          endpoint = `${API_BASE_URL}/api/v1/calendly/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
          requestBody = null; // Will use GET request
        } else {
          endpoint = `${API_BASE_URL}/api/v1/microsoft/connect`;
          requestBody = { authorization_code: code, redirect_uri: `${window.location.origin}/oauth/callback` };
        }

        // Use GET for Calendly, POST for others
        const fetchOptions = providerName === 'Calendly' ? {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        } : {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        };

        const response = await fetch(endpoint, fetchOptions);

        if (response.ok) {
          setStatus('success');
          setMessage(`${providerName} connected successfully!`);
          notifyParent(successType, { provider: providerName.toLowerCase() });

          // For Calendly, redirect to settings page; for others, close the window
          if (providerName === 'Calendly') {
            setTimeout(() => {
              window.location.href = '/settings?section=calendly&connected=true';
            }, 1500);
          } else {
            // Auto-close after a brief delay to show success message
            setTimeout(() => {
              window.close();
            }, 1500);
          }
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
