import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

/**
 * Personal bank statement income form (Non-QM).
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function BankStatementPersonalForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Bank Statement Income (Personal)</h4>
      <p className="income-form-description">
        Non-QM personal deposits. Enter 12 or 24 months of deposits,
        comma-separated.
      </p>

      <div className="income-form-grid">
        <IncomeFormField
          label="Monthly Deposits"
          required
          htmlFor="monthly_deposits"
          className="full-width"
          note="Enter amounts separated by commas or newlines (12-24 months)"
        >
          <textarea
            id="monthly_deposits"
            aria-label="Monthly deposit amounts, comma-separated"
            value={formData.monthly_deposits ?? ''}
            onChange={e => onChange('monthly_deposits', e.target.value)}
            placeholder="15000, 16500, 14800, 17200, 15900, 16100, 14500, 17800, 16300, 15700, 16900, 15200"
            rows={3}
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField
          label="Expense Factor (%)"
          required
          htmlFor="expense_factor"
          note="Percentage of deposits treated as expenses (default 50%)"
        >
          <input
            id="expense_factor"
            aria-label="Expense factor percentage"
            type="number"
            min="0"
            max="100"
            value={formData.expense_factor ?? '50'}
            onChange={e => onChange('expense_factor', e.target.value)}
            placeholder="50"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
