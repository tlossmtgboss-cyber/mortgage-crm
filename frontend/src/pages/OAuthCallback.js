import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import './OAuthCallback.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

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
      const providerName = state?.includes('gmail') ? 'Gmail' : 'Outlook';
      setProvider(providerName);

      if (error) {
        setStatus('error');
        setMessage(errorDescription || `Failed to connect ${providerName}. Please try again.`);
        return;
      }

      if (!code) {
        setStatus('error');
        setMessage('No authorization code received. Please try again.');
        return;
      }

      try {
        const token = localStorage.getItem('token');

        // Determine the correct endpoint based on provider
        const endpoint = providerName === 'Gmail'
          ? `${API_BASE_URL}/api/v1/gmail/callback`
          : `${API_BASE_URL}/api/v1/microsoft/connect`;

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            code,
            redirect_uri: `${window.location.origin}/oauth/callback`
          })
        });

        if (response.ok) {
          setStatus('success');
          setMessage(`${providerName} connected successfully!`);

          // Notify parent window if this is a popup
          if (window.opener) {
            window.opener.postMessage({ type: 'oauth_success', provider: providerName.toLowerCase() }, window.location.origin);
          }
        } else {
          const errorData = await response.json();
          setStatus('error');
          setMessage(errorData.detail || `Failed to connect ${providerName}. Please try again.`);
        }
      } catch (err) {
        console.error('OAuth callback error:', err);
        setStatus('error');
        setMessage('An error occurred while connecting. Please try again.');
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
