import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

const CALCULATION_METHODS = [
  { value: '1', label: 'Method 1: Deposits - Expenses' },
  { value: '2', label: 'Method 2: Expense Ratio' },
  { value: '3', label: 'Method 3: P&L Verification' },
];

/**
 * Business bank statement income form (Non-QM).
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function BankStatementBusinessForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Bank Statement Income (Business)</h4>
      <p className="income-form-description">
        Non-QM business deposits. Enter 12 or 24 months of deposits,
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
            aria-label="Monthly business deposit amounts, comma-separated"
            value={formData.monthly_deposits ?? ''}
            onChange={e => onChange('monthly_deposits', e.target.value)}
            placeholder="25000, 31000, 28500, 33200, 27900, 30100, 29500, 34800, 26300, 31700, 28900, 32200"
            rows={3}
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Calculation Parameters</span>
      </div>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Calculation Method" required htmlFor="method">
          <select
            id="method"
            aria-label="Bank statement calculation method"
            value={formData.method ?? '1'}
            onChange={e => onChange('method', e.target.value)}
            disabled={disabled}
          >
            {CALCULATION_METHODS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </IncomeFormField>

        <IncomeFormField label="Monthly Expenses ($)" htmlFor="monthly_expenses">
          <input
            id="monthly_expenses"
            aria-label="Monthly business expenses"
            type="number"
            min="0"
            value={formData.monthly_expenses ?? ''}
            onChange={e => onChange('monthly_expenses', e.target.value)}
            placeholder="e.g., 15000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField
          label="Expense Ratio (%)"
          htmlFor="expense_ratio"
          note="Percentage of deposits treated as business expenses"
        >
          <input
            id="expense_ratio"
            aria-label="Business expense ratio percentage"
            type="number"
            min="0"
            max="100"
            value={formData.expense_ratio ?? '50'}
            onChange={e => onChange('expense_ratio', e.target.value)}
            placeholder="50"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-grid three-col">
        {formData.method === '3' && (
          <IncomeFormField label="P&L Net Income (Annual)" htmlFor="pl_net_income">
            <input
              id="pl_net_income"
              aria-label="Profit and loss net income, annual"
              type="number"
              min="0"
              value={formData.pl_net_income ?? ''}
              onChange={e => onChange('pl_net_income', e.target.value)}
              placeholder="e.g., 120000"
              disabled={disabled}
            />
          </IncomeFormField>
        )}

        <IncomeFormField label="Ownership %" required htmlFor="ownership_percentage">
          <input
            id="ownership_percentage"
            aria-label="Business ownership percentage"
            type="number"
            min="0"
            max="100"
            value={formData.ownership_percentage ?? '100'}
            onChange={e => onChange('ownership_percentage', e.target.value)}
            placeholder="100"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
