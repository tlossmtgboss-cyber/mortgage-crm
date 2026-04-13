import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

/**
 * Commission income form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function CommissionForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Commission Income</h4>
      <p className="income-form-description">
        Commission minus 2106 unreimbursed expenses
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="YTD Commission ($)" required htmlFor="ytd_commission">
          <input
            id="ytd_commission"
            aria-label="Year-to-date commission"
            type="number"
            min="0"
            value={formData.ytd_commission ?? ''}
            onChange={e => onChange('ytd_commission', e.target.value)}
            placeholder="e.g., 25000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="YTD 2106 Expenses ($)" htmlFor="ytd_expenses_2106">
          <input
            id="ytd_expenses_2106"
            aria-label="Year-to-date 2106 unreimbursed expenses"
            type="number"
            min="0"
            value={formData.ytd_expenses_2106 ?? ''}
            onChange={e => onChange('ytd_expenses_2106', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Year 1</span>
      </div>

      <div className="income-form-grid two-col">
        <IncomeFormField label="Year 1 Commission ($)" required htmlFor="year1_commission">
          <input
            id="year1_commission"
            aria-label="Year 1 commission total"
            type="number"
            min="0"
            value={formData.year1_commission ?? ''}
            onChange={e => onChange('year1_commission', e.target.value)}
            placeholder="e.g., 60000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Year 1 2106 Expenses ($)" htmlFor="year1_expenses_2106">
          <input
            id="year1_expenses_2106"
            aria-label="Year 1 2106 expenses"
            type="number"
            min="0"
            value={formData.year1_expenses_2106 ?? ''}
            onChange={e => onChange('year1_expenses_2106', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Year 2</span>
      </div>

      <div className="income-form-grid two-col">
        <IncomeFormField label="Year 2 Commission ($)" htmlFor="year2_commission">
          <input
            id="year2_commission"
            aria-label="Year 2 commission total"
            type="number"
            min="0"
            value={formData.year2_commission ?? ''}
            onChange={e => onChange('year2_commission', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Year 2 2106 Expenses ($)" htmlFor="year2_expenses_2106">
          <input
            id="year2_expenses_2106"
            aria-label="Year 2 2106 expenses"
            type="number"
            min="0"
            value={formData.year2_expenses_2106 ?? ''}
            onChange={e => onChange('year2_expenses_2106', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
