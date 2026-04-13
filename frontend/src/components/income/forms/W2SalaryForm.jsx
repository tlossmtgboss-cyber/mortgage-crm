import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

const PAY_FREQUENCIES = [
  { value: 'WEEKLY', label: 'Weekly (x52/12)' },
  { value: 'BI_WEEKLY', label: 'Bi-Weekly (x26/12)' },
  { value: 'SEMI_MONTHLY', label: 'Semi-Monthly (x24/12)' },
  { value: 'MONTHLY', label: 'Monthly (x1)' },
];

/**
 * W-2 Salary income form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function W2SalaryForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">W-2 Salary Income</h4>
      <p className="income-form-description">
        Base salary with frequency multipliers
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Base Salary ($)" required htmlFor="base_salary">
          <input
            id="base_salary"
            aria-label="Base salary amount"
            type="number"
            step="0.01"
            min="0"
            value={formData.base_salary ?? ''}
            onChange={e => onChange('base_salary', e.target.value)}
            placeholder="e.g., 5000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Pay Frequency" required htmlFor="pay_frequency">
          <select
            id="pay_frequency"
            aria-label="Pay frequency"
            value={formData.pay_frequency ?? 'MONTHLY'}
            onChange={e => onChange('pay_frequency', e.target.value)}
            disabled={disabled}
          >
            {PAY_FREQUENCIES.map(f => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </IncomeFormField>

        <IncomeFormField label="YTD Salary ($)" htmlFor="ytd_salary">
          <input
            id="ytd_salary"
            aria-label="Year-to-date salary"
            type="number"
            min="0"
            value={formData.ytd_salary ?? ''}
            onChange={e => onChange('ytd_salary', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Historical W-2 Data</span>
      </div>

      <div className="income-form-grid three-col">
        <IncomeFormField label="W-2 Year 1 Earnings ($)" required htmlFor="w2_year1_earnings">
          <input
            id="w2_year1_earnings"
            aria-label="W-2 year 1 earnings"
            type="number"
            min="0"
            value={formData.w2_year1_earnings ?? ''}
            onChange={e => onChange('w2_year1_earnings', e.target.value)}
            placeholder="e.g., 65000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField
          label="W-2 Year 2 Earnings ($)"
          htmlFor="w2_year2_earnings"
          note="Optional per FNMA B3-3.1-01 (03/2026)"
        >
          <input
            id="w2_year2_earnings"
            aria-label="W-2 year 2 earnings, optional"
            type="number"
            min="0"
            value={formData.w2_year2_earnings ?? ''}
            onChange={e => onChange('w2_year2_earnings', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
