import React, { useState } from 'react';
import IncomeCalculator from '../IncomeCalculator';
import UnifiedIncomeCalculator from '../income/UnifiedIncomeCalculator';
import { toast } from '../../utils/toast';

/**
 * Income tab — toggle between unified (14-type) and basic income calculators.
 */
function IncomeTab({ loanId, activeBorrowerId }) {
  const [incomeCalcMode, setIncomeCalcMode] = useState('unified');

  return (
    <div className="info-section">
      <div className="income-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h2 style={{ margin: 0 }}>Income Calculator</h2>
          <p className="circle-description" style={{ margin: '8px 0 0 0' }}>
            Calculate qualifying income following agency guidelines for all 14 income types.
          </p>
        </div>
        <div className="income-calc-toggle" style={{ display: 'flex', gap: '8px' }}>
          <button
            className={`tab-btn ${incomeCalcMode === 'unified' ? 'active' : ''}`}
            onClick={() => setIncomeCalcMode('unified')}
            style={{ padding: '8px 16px', fontSize: '13px' }}
          >
            All 14 Types
          </button>
          <button
            className={`tab-btn ${incomeCalcMode === 'basic' ? 'active' : ''}`}
            onClick={() => setIncomeCalcMode('basic')}
            style={{ padding: '8px 16px', fontSize: '13px' }}
          >
            Quick Calc
          </button>
        </div>
      </div>

      {incomeCalcMode === 'unified' ? (
        <UnifiedIncomeCalculator
          loanId={loanId}
          borrowerId={activeBorrowerId}
          onIncomeCalculated={(result) => {
            console.log('Unified income calculated:', result);
            toast.success(`Monthly income: $${result.monthly_income?.toLocaleString() || 0}`);
          }}
        />
      ) : (
        <IncomeCalculator
          loanId={loanId}
          borrowerId={activeBorrowerId}
          onIncomeCalculated={(result) => {
            console.log('Income calculated:', result);
          }}
        />
      )}
    </div>
  );
}

export default IncomeTab;
