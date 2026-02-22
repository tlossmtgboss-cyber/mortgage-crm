/**
 * Portal Container
 *
 * Smart container that routes to the appropriate portal based on lifecycle stage:
 * - LEAD: Pre-application portal (application form, calculator, resources)
 * - ACTIVE_LOAN: Active loan portal (needs list, milestones, documents)
 * - MUM: Mortgages Under Management (home value, annual refresh, opportunities)
 *
 * Single URL structure: /portal/:slug
 * Stage detection happens via API response
 */

import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import { api } from '../../lib/api';
import './PortalContainer.css';
import PortalOnboardingGuide from '../../components/Portal/PortalOnboardingGuide';

// Lazy load portal components for code splitting
const LeadPortal = lazy(() => import('./LeadPortal'));
const ActiveLoanPortal = lazy(() => import('./ActiveLoanPortal'));
const MUMPortal = lazy(() => import('./MUMPortal'));

// Portal stages enum
export const PortalStage = {
  LEAD: 'lead',
  ACTIVE_LOAN: 'active_loan',
  FUNDED_CELEBRATION: 'funded_celebration',
  MUM: 'mum',
};

// Sub-stages for Active Loan
export const ActiveLoanSubStage = {
  PREAPPROVAL: 'preapproval',
  UNDER_CONTRACT: 'under_contract',
  PROCESSING: 'processing',
  CLEAR_TO_CLOSE: 'clear_to_close',
  FUNDED: 'funded',
};

// Loading spinner component
const PortalLoadingSpinner = () => (
  <div className="portal-loading">
    <div className="loading-content">
      <div className="spinner"></div>
      <p>Loading your portal...</p>
    </div>
  </div>
);

// Error display component
const PortalError = ({ error, onRetry }) => {
  const isAuthError = error?.status === 401 || error?.status === 403;

  return (
    <div className="portal-error">
      <div className="error-container">
        <div className="error-icon">{isAuthError ? '🔐' : '⚠️'}</div>
        <h2>{isAuthError ? 'Access Required' : 'Portal Error'}</h2>
        <p>
          {isAuthError
            ? 'Please use your portal access link to view this page.'
            : error?.message || 'An error occurred loading your portal.'}
        </p>
        <p className="error-help">
          Contact your loan officer for assistance.
        </p>
        {!isAuthError && onRetry && (
          <button className="retry-btn" onClick={onRetry}>
            Try Again
          </button>
        )}
      </div>
    </div>
  );
};

// Funded Celebration overlay (shown briefly after funding)
const FundedCelebration = ({ data, onContinue }) => {
  const borrowerName = data?.contacts?.find(c => c.contact_type === 'borrower')?.first_name || 'there';

  return (
    <div className="funded-celebration">
      <div className="celebration-content">
        <div className="confetti-container">
          {/* Confetti animation handled by CSS */}
          <div className="confetti"></div>
          <div className="confetti"></div>
          <div className="confetti"></div>
        </div>

        <div className="celebration-icon">🎉</div>
        <h1>Congratulations, {borrowerName}!</h1>
        <h2>Your Loan Has Funded!</h2>

        <div className="celebration-details">
          <p>
            Welcome to homeownership! Your loan has officially closed and funded.
          </p>

          <div className="whats-next">
            <h3>What's Next?</h3>
            <ul>
              <li>Your first payment is due on <strong>{data?.loan?.first_payment_date || 'your statement'}</strong></li>
              <li>Your loan will be serviced by <strong>{data?.loan?.servicer || 'your servicer'}</strong></li>
              <li>Keep track of your home value and equity in your new portal</li>
            </ul>
          </div>
        </div>

        <button className="continue-btn" onClick={onContinue}>
          Go to Your Homeowner Portal →
        </button>
      </div>
    </div>
  );
};

// Determine portal stage from workspace data
const detectPortalStage = (workspaceData) => {
  if (!workspaceData) return null;

  const { workspace, loan, application } = workspaceData;
  const status = workspace?.status?.toLowerCase();

  console.log('[detectPortalStage] workspace status:', status, 'loan:', !!loan, 'application:', application?.status);

  // Check if explicitly set in workspace
  if (workspace?.portal_stage) {
    return workspace.portal_stage;
  }

  // Check for MUM/post-close stages first
  if (status === 'mum' || status === 'post_close' || status === 'annual_refresh') {
    return PortalStage.MUM;
  }

  // Check for funded celebration (within 2 days of funding)
  if (loan?.funded_at) {
    const fundedDate = new Date(loan.funded_at);
    const daysSinceFunded = Math.floor((Date.now() - fundedDate) / (1000 * 60 * 60 * 24));

    if (daysSinceFunded <= 2 && status !== 'mum') {
      return PortalStage.FUNDED_CELEBRATION;
    }

    // More than 2 days since funded = MUM
    if (daysSinceFunded > 2) {
      return PortalStage.MUM;
    }
  }

  // Check for funded status
  if (status === 'funded' || loan?.status === 'funded') {
    return PortalStage.MUM;
  }

  // Lead portal — workspace exists but loan not yet disclosed
  if (status === 'lead') {
    return PortalStage.LEAD;
  }

  // Closing sub-stage — maps to ActiveLoanPortal with closing indicator
  if (status === 'closing') {
    return PortalStage.ACTIVE_LOAN;
  }

  // Active loan or application — show Active Loan Portal
  if (status === 'active_loan' || status === 'application') {
    return PortalStage.ACTIVE_LOAN;
  }

  // Default: if workspace exists with unknown status, show Active Loan Portal
  return PortalStage.ACTIVE_LOAN;
};

// Determine sub-stage for active loans
const detectSubStage = (workspaceData) => {
  if (!workspaceData?.loan) return null;

  const { loan, workspace } = workspaceData;
  const loanStatus = loan?.status?.toLowerCase();
  const workspaceStatus = workspace?.status?.toLowerCase();

  // Check clear to close
  if (loan?.clear_to_close_at || loanStatus === 'clear_to_close' || workspaceStatus === 'closing') {
    return ActiveLoanSubStage.CLEAR_TO_CLOSE;
  }

  // Check processing/underwriting
  if (loan?.submitted_to_uw_at || loanStatus === 'processing' || loanStatus === 'underwriting') {
    return ActiveLoanSubStage.PROCESSING;
  }

  // Check under contract
  if (loan?.contract_date || loanStatus === 'under_contract') {
    return ActiveLoanSubStage.UNDER_CONTRACT;
  }

  // Default to preapproval
  return ActiveLoanSubStage.PREAPPROVAL;
};

/**
 * Main Portal Container Component
 */
export default function PortalContainer() {
  const { slug } = useParams();
  const location = useLocation();

  // State
  const [portalData, setPortalData] = useState(null);
  const [stage, setStage] = useState(null);
  const [subStage, setSubStage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCelebration, setShowCelebration] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Get token from URL or localStorage
  const getToken = useCallback(() => {
    const urlParams = new URLSearchParams(location.search);
    const urlToken = urlParams.get('token');

    if (urlToken) {
      localStorage.setItem(`purl_token_${slug}`, urlToken);
      return urlToken;
    }

    return localStorage.getItem(`purl_token_${slug}`);
  }, [location.search, slug]);

  // Fetch portal data
  const fetchPortalData = useCallback(async () => {
    const token = getToken();

    if (!token) {
      setError({ status: 401, message: 'No access token found' });
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Set auth token
      api.setAuthToken(token);

      // Fetch workspace data
      const data = await api.getWorkspaceData(slug);

      if (!data) {
        throw new Error('Portal not found');
      }

      setPortalData(data);

      // Detect stage
      const detectedStage = detectPortalStage(data);
      setStage(detectedStage);

      // Detect sub-stage for active loans
      if (detectedStage === PortalStage.ACTIVE_LOAN) {
        const sub = detectSubStage(data);
        setSubStage(sub);
      }

      // Show celebration if just funded
      if (detectedStage === PortalStage.FUNDED_CELEBRATION) {
        setShowCelebration(true);
      }

      console.log('[PortalContainer] Stage detected:', detectedStage, 'Sub-stage:', detectSubStage(data));

    } catch (err) {
      console.error('[PortalContainer] Error:', err);
      setError({
        status: err.status || 500,
        message: err.message || 'Failed to load portal',
      });
    } finally {
      setLoading(false);
    }
  }, [slug, getToken]);

  // Load data on mount
  useEffect(() => {
    fetchPortalData();
  }, [fetchPortalData]);

  // Auto-refresh polling — re-fetch every 60s so stage transitions appear
  // without requiring a manual page refresh
  useEffect(() => {
    if (loading || error) return;

    const interval = setInterval(() => {
      fetchPortalData();
    }, 60000);

    return () => clearInterval(interval);
  }, [loading, error, fetchPortalData]);

  // Check if should show onboarding (after data loads)
  useEffect(() => {
    if (portalData && !loading && !error) {
      const storageKey = `portal_onboarding_${slug}`;
      const hasSeenGuide = localStorage.getItem(storageKey);
      // Show onboarding for first-time visitors
      if (!hasSeenGuide) {
        // Small delay to let the UI render
        const timer = setTimeout(() => setShowOnboarding(true), 800);
        return () => clearTimeout(timer);
      }
    }
  }, [portalData, loading, error, slug]);

  // Restart the portal tour
  const restartTour = useCallback(() => {
    const storageKey = `portal_onboarding_${slug}`;
    localStorage.removeItem(storageKey);
    setShowOnboarding(true);
  }, [slug]);

  // Handle celebration dismiss
  const handleCelebrationContinue = () => {
    setShowCelebration(false);
    setStage(PortalStage.MUM);
  };

  // No token
  if (!getToken()) {
    return <PortalError error={{ status: 401, message: 'Access required' }} />;
  }

  // Loading state
  if (loading) {
    return <PortalLoadingSpinner />;
  }

  // Error state
  if (error) {
    return <PortalError error={error} onRetry={fetchPortalData} />;
  }

  // Show celebration overlay if applicable
  if (showCelebration) {
    return (
      <FundedCelebration
        data={portalData}
        onContinue={handleCelebrationContinue}
      />
    );
  }

  // Render appropriate portal based on stage
  return (
    <>
      <Suspense fallback={<PortalLoadingSpinner />}>
        {stage === PortalStage.LEAD && (
          <LeadPortal
            data={portalData}
            slug={slug}
            onRefresh={fetchPortalData}
            onRestartTour={restartTour}
          />
        )}

        {stage === PortalStage.ACTIVE_LOAN && (
          <ActiveLoanPortal
            data={portalData}
            slug={slug}
            subStage={subStage}
            onRefresh={fetchPortalData}
            onRestartTour={restartTour}
          />
        )}

        {stage === PortalStage.MUM && (
          <MUMPortal
            data={portalData}
            slug={slug}
            onRefresh={fetchPortalData}
            onRestartTour={restartTour}
          />
        )}
      </Suspense>

      {/* Onboarding Guide for first-time visitors */}
      {showOnboarding && (
        <PortalOnboardingGuide
          workspaceSlug={slug}
          stage={stage}
          onComplete={() => setShowOnboarding(false)}
        />
      )}
    </>
  );
}
