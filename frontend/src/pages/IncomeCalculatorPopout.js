/**
 * Income Calculator Popout Page
 * Standalone version of income calculator for popout window
 */
import React from 'react';
import UnifiedIncomeCalculator from '../components/income/UnifiedIncomeCalculator';

function IncomeCalculatorPopout() {
  // Get parameters from URL
  const params = new URLSearchParams(window.location.search);
  const loanId = params.get('loanId');
  const borrowerId = params.get('borrowerId');
  const borrowerName = params.get('borrowerName') || 'Borrower';

  return (
    <div style={{ padding: '20px', minHeight: '100vh', background: '#f9fafb' }}>
      <UnifiedIncomeCalculator
        loanId={loanId ? parseInt(loanId) : null}
        borrowerId={borrowerId ? parseInt(borrowerId) : null}
        borrowerName={borrowerName}
        isPopout={true}
      />
    </div>
  );
}

export default IncomeCalculatorPopout;
