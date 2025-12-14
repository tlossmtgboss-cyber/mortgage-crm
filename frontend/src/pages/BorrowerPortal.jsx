/**
 * BorrowerPortal Page
 *
 * Public-facing borrower portal that displays loan progress,
 * milestones, documents, and timeline information.
 */

import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import BorrowerPortalDashboard, { MumPortalDashboard } from '../components/portal/BorrowerPortalDashboard';
import { borrowerPortalApi } from '../services/portalApi';
import './BorrowerPortal.css';

export default function BorrowerPortal() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const [portalData, setPortalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadPortal = async () => {
      try {
        setLoading(true);

        // Try token-based access first (magic link)
        if (token) {
          const data = await borrowerPortalApi.getPortalByToken(token);
          setPortalData(data);
        } else {
          // Fall back to loan_id from query params (authenticated access)
          const loanId = searchParams.get('loan_id');
          if (loanId) {
            const data = await borrowerPortalApi.getDashboard(loanId);
            setPortalData(data);
          } else {
            setError('No portal access token or loan ID provided');
          }
        }
      } catch (err) {
        console.error('Portal load error:', err);
        setError(err.message || 'Failed to load portal');
      } finally {
        setLoading(false);
      }
    };

    loadPortal();
  }, [token, searchParams]);

  if (loading) {
    return (
      <div className="portal-page loading">
        <div className="portal-loader">
          <div className="loader-spinner" />
          <p>Loading your portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portal-page error">
        <div className="portal-error-card">
          <span className="error-icon">🔒</span>
          <h1>Portal Access Error</h1>
          <p>{error}</p>
          <p className="help-text">
            If you received a link to access your portal, please make sure you're using the complete link.
            Contact your loan officer if you need assistance.
          </p>
        </div>
      </div>
    );
  }

  // Determine which dashboard to show based on lifecycle stage
  const isMumStage = portalData?.lifecycle?.stage === 'MUM' ||
                     portalData?.lifecycle?.stage === 'ANNUAL_REFRESH';

  return (
    <div className="portal-page">
      <div className="portal-container">
        {isMumStage ? (
          <MumPortalDashboard
            loanId={portalData.loan_id}
            borrowerName={portalData.borrower_name}
          />
        ) : (
          <BorrowerPortalDashboard
            loanId={portalData.loan_id}
            borrowerName={portalData.borrower_name}
          />
        )}
      </div>

      {/* Portal Footer */}
      <footer className="portal-footer">
        <p>Powered by Perennia AI</p>
        <p className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <span className="divider">|</span>
          <a href="/terms">Terms of Service</a>
        </p>
      </footer>
    </div>
  );
}
