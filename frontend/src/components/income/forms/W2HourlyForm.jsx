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
 * W-2 Hourly income form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function W2HourlyForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">W-2 Hourly Income</h4>
      <p className="income-form-description">
        Per Hour x # of hours x 52/12 = Monthly Income
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Hourly Rate ($)" required htmlFor="hourly_rate">
          <input
            id="hourly_rate"
            aria-label="Hourly rate in dollars"
            type="number"
            step="0.01"
            min="0"
            value={formData.hourly_rate ?? ''}
            onChange={e => onChange('hourly_rate', e.target.value)}
            placeholder="e.g., 25.00"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Hours per Period" required htmlFor="hours_per_period">
          <input
            id="hours_per_period"
            aria-label="Hours worked per pay period"
            type="number"
            min="0"
            value={formData.hours_per_period ?? ''}
            onChange={e => onChange('hours_per_period', e.target.value)}
            placeholder="40"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Pay Frequency" required htmlFor="pay_frequency">
          <select
            id="pay_frequency"
            aria-label="Pay frequency"
            value={formData.pay_frequency ?? 'BI_WEEKLY'}
            onChange={e => onChange('pay_frequency', e.target.value)}
            disabled={disabled}
          >
            {PAY_FREQUENCIES.map(f => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Historical Data (for averaging)</span>
      </div>

      <div className="income-form-grid four-col">
        <IncomeFormField label="YTD Earnings ($)" htmlFor="ytd_earnings">
          <input
            id="ytd_earnings"
            aria-label="Year-to-date earnings"
            type="number"
            min="0"
            value={formData.ytd_earnings ?? ''}
            onChange={e => onChange('ytd_earnings', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="W-2 Year 1 Earnings ($)" required htmlFor="w2_year1_earnings">
          <input
            id="w2_year1_earnings"
            aria-label="W-2 year 1 earnings"
            type="number"
            min="0"
            value={formData.w2_year1_earnings ?? ''}
            onChange={e => onChange('w2_year1_earnings', e.target.value)}
            placeholder="e.g., 52000"
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
