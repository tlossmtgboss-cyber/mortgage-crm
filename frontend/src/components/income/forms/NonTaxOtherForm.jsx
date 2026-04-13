import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

const INCOME_TYPE_OPTIONS = [
  { value: 'pension', label: 'Pension' },
  { value: 'ira', label: 'IRA Distribution' },
  { value: 'child_support', label: 'Child Support' },
  { value: 'disability', label: 'Disability' },
];

/**
 * Other non-taxable income form (pension, IRA, child support, disability).
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function NonTaxOtherForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Other Non-Taxable Income</h4>
      <p className="income-form-description">
        Pension, IRA, child support, disability (25% gross-up if non-taxable)
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Income Type" required htmlFor="income_type">
          <select
            id="income_type"
            aria-label="Type of non-taxable income"
            value={formData.income_type ?? 'pension'}
            onChange={e => onChange('income_type', e.target.value)}
            disabled={disabled}
          >
            {INCOME_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </IncomeFormField>

        <IncomeFormField label="Annual Amount ($)" required htmlFor="annual_amount">
          <input
            id="annual_amount"
            aria-label="Annual income amount"
            type="number"
            min="0"
            value={formData.annual_amount ?? ''}
            onChange={e => onChange('annual_amount', e.target.value)}
            placeholder="e.g., 18000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Is Taxable (no gross-up)" htmlFor="is_taxable" checkbox>
          <input
            id="is_taxable"
            aria-label="Income is taxable, no gross-up applied"
            type="checkbox"
            checked={formData.is_taxable ?? false}
            onChange={e => onChange('is_taxable', e.target.checked)}
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
