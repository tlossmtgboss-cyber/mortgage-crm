import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

/**
 * Social Security non-taxable income form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function NonTaxSSForm({ formData, onChange, disabled = false }) {
  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Social Security Income</h4>
      <p className="income-form-description">
        Non-taxable portion receives 25% gross-up
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Annual Benefit ($)" required htmlFor="annual_benefit">
          <input
            id="annual_benefit"
            aria-label="Annual Social Security benefit"
            type="number"
            min="0"
            value={formData.annual_benefit ?? ''}
            onChange={e => onChange('annual_benefit', e.target.value)}
            placeholder="e.g., 24000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField
          label="Has SSA-1099 Documentation"
          htmlFor="has_documentation"
          checkbox
        >
          <input
            id="has_documentation"
            aria-label="Has SSA-1099 documentation"
            type="checkbox"
            checked={formData.has_documentation ?? false}
            onChange={e => onChange('has_documentation', e.target.checked)}
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      {formData.has_documentation && (
        <>
          <div className="income-form-divider">
            <span>SSA-1099 Breakdown</span>
          </div>

          <div className="income-form-grid two-col">
            <IncomeFormField label="Taxable Portion ($)" htmlFor="taxable_portion">
              <input
                id="taxable_portion"
                aria-label="Taxable portion from 1040 Line 5b"
                type="number"
                min="0"
                value={formData.taxable_portion ?? ''}
                onChange={e => onChange('taxable_portion', e.target.value)}
                placeholder="From 1040 Line 5b"
                disabled={disabled}
              />
            </IncomeFormField>

            <IncomeFormField label="Non-Taxable Portion ($)" htmlFor="non_taxable_portion">
              <input
                id="non_taxable_portion"
                aria-label="Non-taxable portion, Line 5a minus 5b"
                type="number"
                min="0"
                value={formData.non_taxable_portion ?? ''}
                onChange={e => onChange('non_taxable_portion', e.target.value)}
                placeholder="Line 5a - 5b"
                disabled={disabled}
              />
            </IncomeFormField>
          </div>
        </>
      )}

      {!formData.has_documentation && (
        <p className="income-form-field-note" style={{ marginTop: 12 }}>
          Without documentation: 85% taxable, 15% non-taxable (25% gross-up on
          non-taxable)
        </p>
      )}
    </div>
  );
}
