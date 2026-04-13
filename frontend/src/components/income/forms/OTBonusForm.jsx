import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

/**
 * Overtime & Bonus income form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function OTBonusForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Overtime & Bonus Income</h4>
      <p className="income-form-description">
        2-year average, uses lowest calculation
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="YTD OT/Bonus ($)" required htmlFor="ytd_ot_bonus">
          <input
            id="ytd_ot_bonus"
            aria-label="Year-to-date overtime and bonus"
            type="number"
            min="0"
            value={formData.ytd_ot_bonus ?? ''}
            onChange={e => onChange('ytd_ot_bonus', e.target.value)}
            placeholder="e.g., 5000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="YTD Months" required htmlFor="ytd_months">
          <input
            id="ytd_months"
            aria-label="Number of months year-to-date"
            type="number"
            min="1"
            max="12"
            value={formData.ytd_months ?? ''}
            onChange={e => onChange('ytd_months', e.target.value)}
            placeholder="e.g., 6"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Prior Year Data</span>
      </div>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Year 1 OT/Bonus ($)" required htmlFor="year1_ot_bonus">
          <input
            id="year1_ot_bonus"
            aria-label="Year 1 overtime and bonus total"
            type="number"
            min="0"
            value={formData.year1_ot_bonus ?? ''}
            onChange={e => onChange('year1_ot_bonus', e.target.value)}
            placeholder="e.g., 12000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Year 1 Months" required htmlFor="year1_months">
          <input
            id="year1_months"
            aria-label="Number of months in year 1"
            type="number"
            min="1"
            max="12"
            value={formData.year1_months ?? ''}
            onChange={e => onChange('year1_months', e.target.value)}
            placeholder="12"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Year 2 OT/Bonus ($)" htmlFor="year2_ot_bonus">
          <input
            id="year2_ot_bonus"
            aria-label="Year 2 overtime and bonus total"
            type="number"
            min="0"
            value={formData.year2_ot_bonus ?? ''}
            onChange={e => onChange('year2_ot_bonus', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Year 2 Months" htmlFor="year2_months">
          <input
            id="year2_months"
            aria-label="Number of months in year 2"
            type="number"
            min="1"
            max="12"
            value={formData.year2_months ?? ''}
            onChange={e => onChange('year2_months', e.target.value)}
            placeholder="12"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
