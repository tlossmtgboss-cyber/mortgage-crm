import React from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

const BUSINESS_TYPES = [
  { value: 'sole_prop', label: 'Sole Proprietorship (Sch C)' },
  { value: 's_corp', label: 'S-Corporation (K-1 1120S)' },
  { value: 'partnership', label: 'Partnership (K-1 1065)' },
  { value: 'c_corp', label: 'C-Corporation (1120)' },
];

/**
 * Self-employment income form (Fannie Mae 1084).
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function SelfEmployment1084Form({ formData, onChange, disabled = false }) {
  const businessType = formData.business_type ?? 'sole_prop';

  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Self-Employment (Fannie Mae 1084)</h4>
      <p className="income-form-description">
        Schedule C, K-1, or 1120 with depreciation add-backs
      </p>

      <div className="income-form-grid three-col">
        <IncomeFormField label="Business Name" required htmlFor="business_name">
          <input
            id="business_name"
            aria-label="Business name"
            type="text"
            value={formData.business_name ?? ''}
            onChange={e => onChange('business_name', e.target.value)}
            placeholder="e.g., Acme Consulting LLC"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Business Type" required htmlFor="business_type">
          <select
            id="business_type"
            aria-label="Business entity type"
            value={businessType}
            onChange={e => onChange('business_type', e.target.value)}
            disabled={disabled}
          >
            {BUSINESS_TYPES.map(bt => (
              <option key={bt.value} value={bt.value}>{bt.label}</option>
            ))}
          </select>
        </IncomeFormField>

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

      {/* Year 1 */}
      <div className="income-form-divider">
        <span>Year 1</span>
      </div>

      <div className="income-form-grid two-col">
        <IncomeFormField label="Net Profit ($)" required htmlFor="year1_net_profit">
          <input
            id="year1_net_profit"
            aria-label="Year 1 net profit"
            type="number"
            value={formData.year1_net_profit ?? ''}
            onChange={e => onChange('year1_net_profit', e.target.value)}
            placeholder="e.g., 85000"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Depreciation ($)" htmlFor="year1_depreciation">
          <input
            id="year1_depreciation"
            aria-label="Year 1 depreciation add-back"
            type="number"
            min="0"
            value={formData.year1_depreciation ?? ''}
            onChange={e => onChange('year1_depreciation', e.target.value)}
            placeholder="e.g., 5000"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      {/* Year 2 */}
      <div className="income-form-divider">
        <span>Year 2</span>
      </div>

      <div className="income-form-grid two-col">
        <IncomeFormField label="Net Profit ($)" htmlFor="year2_net_profit">
          <input
            id="year2_net_profit"
            aria-label="Year 2 net profit"
            type="number"
            value={formData.year2_net_profit ?? ''}
            onChange={e => onChange('year2_net_profit', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Depreciation ($)" htmlFor="year2_depreciation">
          <input
            id="year2_depreciation"
            aria-label="Year 2 depreciation add-back"
            type="number"
            min="0"
            value={formData.year2_depreciation ?? ''}
            onChange={e => onChange('year2_depreciation', e.target.value)}
            placeholder="Optional"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>
    </div>
  );
}
