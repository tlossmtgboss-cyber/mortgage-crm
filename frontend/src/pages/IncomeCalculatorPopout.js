import React from 'react';
import { useSearchParams } from 'react-router-dom';
import IncomeCalculator from '../components/IncomeCalculator';

/**
 * IncomeCalculatorPopout - Standalone income calculator for multi-monitor viewing
 *
 * Opens in a separate window to allow loan officers to view income calculations
 * alongside other application screens.
 *
 * URL params:
 * - loanId: The loan ID to calculate income for
 * - borrowerId: Optional borrower ID (defaults to 1)
 */
function IncomeCalculatorPopout() {
  const [searchParams] = useSearchParams();
  const loanId = searchParams.get('loanId') || '';
  const borrowerId = parseInt(searchParams.get('borrowerId') || '1', 10);

  return (
    <div style={{
      padding: '20px',
      maxWidth: '900px',
      margin: '0 auto',
      minHeight: '100vh',
      backgroundColor: '#f8fafc',
    }}>
      <div style={{
        marginBottom: '20px',
        padding: '15px',
        backgroundColor: '#fff',
        borderRadius: '8px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }}>
        <h1 style={{
          margin: '0 0 5px 0',
          fontSize: '24px',
          fontWeight: '600',
          color: '#1e293b',
        }}>
          Income Calculator
        </h1>
        {loanId && (
          <p style={{
            margin: 0,
            fontSize: '14px',
            color: '#64748b',
          }}>
            Loan ID: {loanId}
          </p>
        )}
      </div>

      <IncomeCalculator
        loanId={loanId}
        borrowerId={borrowerId}
        onIncomeCalculated={(result) => {
          // Optionally notify parent window of calculation results
          if (window.opener) {
            window.opener.postMessage({
              type: 'INCOME_CALCULATED',
              loanId,
              result,
            }, '*');
          }
        }}
      />
    </div>
  );
}

export default IncomeCalculatorPopout;
