/**
 * BorrowerPortal Page
 *
 * Public-facing borrower portal that displays loan progress,
 * milestones, documents, and timeline information.
 * Supports multi-loan switching for borrowers with multiple loans.
 */

import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import BorrowerPortalDashboard, { MumPortalDashboard } from '../components/portal/BorrowerPortalDashboard';
import { borrowerPortalApi } from '../services/portalApi';
import { PortalProvider, usePortal } from '../contexts/PortalContext';
import { LoanSelector, PortalModeIndicator } from '../components/portal';
import './BorrowerPortal.css';

/**
 * Portal Header with Multi-Loan Support
 */
function PortalHeader({ borrowerName }) {
  const { hasMultipleLoans, currentLoan } = usePortal();

  return (
    <div className="portal-top-header">
      <div className="portal-branding">
        <h2 className="portal-title">Borrower Portal</h2>
        {borrowerName && <span className="portal-user">Welcome, {borrowerName}</span>}
      </div>

      <div className="portal-header-controls">
        {/* Show loan selector if borrower has multiple loans */}
        {hasMultipleLoans && (
          <LoanSelector className="portal-loan-selector" showModeIndicator={false} />
        )}

        {/* Show mode indicator */}
        {currentLoan && (
          <PortalModeIndicator size="small" showCounts={false} />
        )}
      </div>
    </div>
  );
}

/**
 * Inner portal content that uses portal context
 */
function BorrowerPortalContent({ initialPortalData }) {
  const { currentLoan, portalMode, switching } = usePortal();

  // Use currentLoan from context if available, otherwise use initial data
  const activeLoanId = currentLoan?.id || initialPortalData?.loan_id;
  const borrowerName = initialPortalData?.borrower_name;

  // Determine which dashboard to show based on lifecycle stage or portal mode
  const isMumStage = initialPortalData?.lifecycle?.stage === 'MUM' ||
                     initialPortalData?.lifecycle?.stage === 'ANNUAL_REFRESH' ||
                     portalMode === 'servicing';

  // Show loading overlay when switching loans
  if (switching) {
    return (
      <>
        <PortalHeader borrowerName={borrowerName} />
        <div className="portal-container">
          <div className="portal-switching-overlay">
            <div className="loader-spinner" />
            <p>Switching loan...</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      {/* Multi-loan header */}
      <PortalHeader borrowerName={borrowerName} />

      {/* Dashboard content */}
      <div className="portal-container">
        {isMumStage ? (
          <MumPortalDashboard
            loanId={activeLoanId}
            borrowerName={borrowerName}
          />
        ) : (
          <BorrowerPortalDashboard
            loanId={activeLoanId}
            borrowerName={borrowerName}
          />
        )}
      </div>
    </>
  );
}

/**
 * Portal wrapper without multi-loan context (fallback for single loan access)
 */
function SingleLoanPortal({ portalData }) {
  // Determine which dashboard to show based on lifecycle stage
  const isMumStage = portalData?.lifecycle?.stage === 'MUM' ||
                     portalData?.lifecycle?.stage === 'ANNUAL_REFRESH';

  return (
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
  );
}

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

  // Extract workspace_id and borrower_profile_id from portal data for multi-loan context
  const workspaceId = portalData?.workspace_id;
  const borrowerProfileId = portalData?.borrower_profile_id || portalData?.borrower_id;

  // If we have multi-loan context info, use PortalProvider for loan switching
  const hasMultiLoanContext = workspaceId && borrowerProfileId;

  return (
    <div className="portal-page">
      {hasMultiLoanContext ? (
        <PortalProvider
          workspaceId={workspaceId}
          borrowerProfileId={borrowerProfileId}
        >
          <BorrowerPortalContent initialPortalData={portalData} />
        </PortalProvider>
      ) : (
        <SingleLoanPortal portalData={portalData} />
      )}

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
