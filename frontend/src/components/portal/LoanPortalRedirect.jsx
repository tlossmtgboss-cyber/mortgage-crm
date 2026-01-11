/**
 * LoanPortalRedirect Component
 *
 * Redirects loan ID URLs to the proper borrower portal with token authentication.
 * Supports both portal_loans.id and crm_deal_id lookups.
 */

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

const API_BASE = process.env.REACT_APP_API_URL || '';

export default function LoanPortalRedirect() {
  const { loanId } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const lookupPortal = async () => {
      if (!loanId) {
        setError('No loan ID provided');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/portal/by-loan/${loanId}`);

        if (!response.ok) {
          if (response.status === 404) {
            setError('Loan not found. Please check the loan ID and try again.');
          } else {
            setError('Failed to load portal. Please try again later.');
          }
          setLoading(false);
          return;
        }

        const data = await response.json();

        if (data.found && data.redirect_url) {
          // Redirect to the borrower portal with the access token
          navigate(data.redirect_url, { replace: true });
        } else if (data.found && data.access_token) {
          // Fallback: construct the URL ourselves
          navigate(`/borrower-portal/${data.access_token}`, { replace: true });
        } else if (data.found) {
          // No token available, try direct loan access via query param
          navigate(`/borrower-portal?loan_id=${data.portal_loan_id || loanId}`, { replace: true });
        } else {
          setError('Portal not available for this loan.');
          setLoading(false);
        }
      } catch (err) {
        console.error('Portal lookup error:', err);
        setError('An error occurred while looking up the portal.');
        setLoading(false);
      }
    };

    lookupPortal();
  }, [loanId, navigate]);

  if (loading) {
    return (
      <div className="portal-redirect-loading" style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f7fa',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}>
        <div className="loader-spinner" style={{
          width: '48px',
          height: '48px',
          border: '4px solid #e2e8f0',
          borderTopColor: '#4c6ef5',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }} />
        <p style={{ marginTop: '16px', color: '#64748b' }}>
          Loading portal...
        </p>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portal-redirect-error" style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f7fa',
        padding: '24px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}>
        <div style={{
          backgroundColor: 'white',
          padding: '32px',
          borderRadius: '12px',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
          textAlign: 'center',
          maxWidth: '400px',
        }}>
          <span style={{ fontSize: '48px', marginBottom: '16px', display: 'block' }}>
            🔒
          </span>
          <h1 style={{ fontSize: '24px', fontWeight: '600', color: '#1a202c', marginBottom: '8px' }}>
            Portal Access Error
          </h1>
          <p style={{ color: '#64748b', marginBottom: '24px' }}>
            {error}
          </p>
          <button
            onClick={() => navigate(-1)}
            style={{
              padding: '10px 24px',
              backgroundColor: '#4c6ef5',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
            }}
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return null;
}
