/**
 * Portal Test Page
 * Temporary page to test the multi-loan portal components
 */
import React from 'react';
import { PortalProvider, usePortal, PORTAL_MODES } from '../contexts/PortalContext';
import { LoanSelector, PortalModeIndicator } from '../components/portal';
import { ModeBadge } from '../components/portal/PortalModeIndicator';

// Inner component that uses portal context
function PortalTestContent() {
  const {
    currentLoan,
    availableLoans,
    portalMode,
    loading,
    error,
    transactionLoansCount,
    servicingLoansCount,
    hasMultipleLoans,
  } = usePortal();

  if (loading) {
    return <div className="p-8">Loading portal context...</div>;
  }

  if (error) {
    return <div className="p-8 text-red-600">Error: {error}</div>;
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Portal Components Test</h1>
      
      {/* PortalModeIndicator test */}
      <section className="mb-8 p-4 border rounded-lg">
        <h2 className="text-lg font-semibold mb-4">PortalModeIndicator</h2>
        <div className="space-y-4">
          <div>
            <span className="text-sm text-gray-500 mr-2">Default size:</span>
            <PortalModeIndicator />
          </div>
          <div>
            <span className="text-sm text-gray-500 mr-2">With counts:</span>
            <PortalModeIndicator showCounts={true} />
          </div>
          <div>
            <span className="text-sm text-gray-500 mr-2">Small size:</span>
            <PortalModeIndicator size="small" />
          </div>
          <div>
            <span className="text-sm text-gray-500 mr-2">Large size:</span>
            <PortalModeIndicator size="large" />
          </div>
        </div>
      </section>

      {/* ModeBadge standalone test */}
      <section className="mb-8 p-4 border rounded-lg">
        <h2 className="text-lg font-semibold mb-4">ModeBadge (Standalone)</h2>
        <div className="flex gap-4">
          <ModeBadge mode="transaction" />
          <ModeBadge mode="servicing" />
          <ModeBadge mode="transaction" size="small" />
          <ModeBadge mode="servicing" showIcon={false} />
        </div>
      </section>

      {/* LoanSelector test */}
      <section className="mb-8 p-4 border rounded-lg">
        <h2 className="text-lg font-semibold mb-4">LoanSelector</h2>
        <LoanSelector className="max-w-md" />
        {!hasMultipleLoans && (
          <p className="mt-2 text-sm text-gray-500">
            (LoanSelector is hidden when there's only one loan)
          </p>
        )}
      </section>

      {/* Context state display */}
      <section className="mb-8 p-4 border rounded-lg bg-gray-50">
        <h2 className="text-lg font-semibold mb-4">Portal Context State</h2>
        <pre className="text-xs overflow-auto">
          {JSON.stringify({
            portalMode,
            transactionLoansCount,
            servicingLoansCount,
            hasMultipleLoans,
            currentLoan: currentLoan ? {
              id: currentLoan.id,
              loan_number: currentLoan.loan_number,
              status: currentLoan.status,
              portal_mode: currentLoan.portal_mode,
            } : null,
            availableLoansCount: availableLoans.length,
          }, null, 2)}
        </pre>
      </section>
    </div>
  );
}

// Main test page with provider
export default function PortalTest() {
  // Use workspace 5 which has test data
  return (
    <PortalProvider borrowerProfileId="test-borrower" workspaceId={5}>
      <PortalTestContent />
    </PortalProvider>
  );
}
