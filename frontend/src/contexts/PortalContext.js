import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';

// Portal modes
export const PORTAL_MODES = {
  TRANSACTION: 'transaction',
  SERVICING: 'servicing',
};

// Default portal state
const defaultPortalState = {
  sessionId: null,
  borrowerProfileId: null,
  workspaceId: null,
  currentLoan: null,
  portalMode: PORTAL_MODES.TRANSACTION,
  availableLoans: [],
  transactionLoansCount: 0,
  servicingLoansCount: 0,
  hasMultipleLoans: false,
};

// Context
const PortalContext = createContext(null);

export function PortalProvider({ children, borrowerProfileId, workspaceId }) {
  // Portal state
  const [portalState, setPortalState] = useState({
    ...defaultPortalState,
    borrowerProfileId,
    workspaceId,
  });

  // Loading states
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState(null);

  // Fetch portal context from API
  const fetchPortalContext = useCallback(async (loanId = null) => {
    if (!borrowerProfileId || !workspaceId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        borrower_profile_id: borrowerProfileId,
        workspace_id: workspaceId,
      });

      if (loanId) {
        params.append('loan_id', loanId);
      }

      const response = await fetch(
        `${API_BASE_URL}/api/portal/multi-loan/context?${params}`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch portal context');
      }

      const data = await response.json();

      setPortalState({
        sessionId: data.session_id,
        borrowerProfileId: data.borrower_profile_id,
        workspaceId,
        currentLoan: data.current_loan,
        portalMode: data.portal_mode || PORTAL_MODES.TRANSACTION,
        availableLoans: data.available_loans || [],
        transactionLoansCount: data.transaction_loans_count || 0,
        servicingLoansCount: data.servicing_loans_count || 0,
        hasMultipleLoans: data.has_multiple_loans || false,
      });
    } catch (err) {
      console.error('Failed to fetch portal context:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [borrowerProfileId, workspaceId]);

  // Switch to a different loan
  const switchLoan = useCallback(async (loanId, reason = null) => {
    if (!portalState.sessionId) {
      console.error('No session ID available');
      return;
    }

    setSwitching(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        session_id: portalState.sessionId,
        borrower_profile_id: borrowerProfileId,
        workspace_id: workspaceId,
      });

      if (portalState.currentLoan?.id) {
        params.append('current_loan_id', portalState.currentLoan.id);
      }

      const response = await fetch(
        `${API_BASE_URL}/api/portal/multi-loan/loans/switch?${params}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            loan_id: loanId,
            reason,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to switch loan');
      }

      const data = await response.json();

      if (data.success && data.context) {
        setPortalState({
          sessionId: data.context.session_id,
          borrowerProfileId: data.context.borrower_profile_id,
          workspaceId,
          currentLoan: data.context.current_loan,
          portalMode: data.context.portal_mode || PORTAL_MODES.TRANSACTION,
          availableLoans: data.context.available_loans || [],
          transactionLoansCount: data.context.transaction_loans_count || 0,
          servicingLoansCount: data.context.servicing_loans_count || 0,
          hasMultipleLoans: data.context.has_multiple_loans || false,
        });
      }

      return data;
    } catch (err) {
      console.error('Failed to switch loan:', err);
      setError(err.message);
      throw err;
    } finally {
      setSwitching(false);
    }
  }, [portalState.sessionId, portalState.currentLoan, borrowerProfileId, workspaceId]);

  // Log portal activity
  const logActivity = useCallback(async (activityType, activityData = null, pagePath = null) => {
    if (!portalState.sessionId) return;

    try {
      const params = new URLSearchParams({
        session_id: portalState.sessionId,
        borrower_profile_id: borrowerProfileId,
      });

      if (portalState.currentLoan?.id) {
        params.append('loan_id', portalState.currentLoan.id);
      }

      await fetch(
        `${API_BASE_URL}/api/portal/multi-loan/activity?${params}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            activity_type: activityType,
            activity_data: activityData,
            page_path: pagePath,
          }),
        }
      );
    } catch (err) {
      console.error('Failed to log activity:', err);
    }
  }, [portalState.sessionId, portalState.currentLoan, borrowerProfileId]);

  // Get loan history chain
  const getLoanHistory = useCallback(async (loanId = null) => {
    const targetLoanId = loanId || portalState.currentLoan?.id;
    if (!targetLoanId) return [];

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/portal/multi-loan/loans/${targetLoanId}/history`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch loan history');
      }

      const data = await response.json();
      return data.history || [];
    } catch (err) {
      console.error('Failed to fetch loan history:', err);
      return [];
    }
  }, [portalState.currentLoan]);

  // Initialize portal context on mount
  useEffect(() => {
    fetchPortalContext();
  }, [fetchPortalContext]);

  // Check if current mode is transaction
  const isTransactionMode = portalState.portalMode === PORTAL_MODES.TRANSACTION;

  // Check if current mode is servicing
  const isServicingMode = portalState.portalMode === PORTAL_MODES.SERVICING;

  // Get loans filtered by mode
  const getTransactionLoans = useCallback(() => {
    return portalState.availableLoans.filter(
      loan => loan.portal_mode === PORTAL_MODES.TRANSACTION
    );
  }, [portalState.availableLoans]);

  const getServicingLoans = useCallback(() => {
    return portalState.availableLoans.filter(
      loan => loan.portal_mode === PORTAL_MODES.SERVICING
    );
  }, [portalState.availableLoans]);

  // Format address for display
  const formatAddress = useCallback((loan) => {
    if (!loan) return '';

    if (typeof loan.property_address === 'string') {
      return loan.property_address;
    }

    if (typeof loan.property_address === 'object' && loan.property_address) {
      const addr = loan.property_address;
      return `${addr.street || ''}, ${addr.city || ''} ${addr.state || ''}`.trim();
    }

    return 'Address not available';
  }, []);

  // Format currency for display
  const formatCurrency = useCallback((amount) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  }, []);

  const value = {
    // State
    ...portalState,
    loading,
    switching,
    error,

    // Mode helpers
    isTransactionMode,
    isServicingMode,
    PORTAL_MODES,

    // Actions
    fetchPortalContext,
    switchLoan,
    logActivity,
    getLoanHistory,

    // Filtered loan getters
    getTransactionLoans,
    getServicingLoans,

    // Utilities
    formatAddress,
    formatCurrency,
  };

  return (
    <PortalContext.Provider value={value}>
      {children}
    </PortalContext.Provider>
  );
}

// Custom hook for using the portal context
export function usePortal() {
  const context = useContext(PortalContext);
  if (!context) {
    throw new Error('usePortal must be used within a PortalProvider');
  }
  return context;
}

export default PortalContext;
