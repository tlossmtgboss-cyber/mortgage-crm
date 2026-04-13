import React, { useState } from 'react';
import IncomeFormField from './IncomeFormField';
import './forms.css';

/**
 * Rental income (Schedule E) form.
 *
 * @param {Object}   props
 * @param {Object}   props.formData - Current field values
 * @param {Function} props.onChange  - (fieldName, value) => void
 * @param {boolean}  [props.disabled]
 */
export default function RentalScheduleEForm({ formData, onChange, disabled = false }) {
  const [showYear2, setShowYear2] = useState(false);

  return (
    <div className="uic-form-section">
      <h4 className="income-form-section-heading">Rental Income (Schedule E)</h4>
      <p className="income-form-description">
        Gross rents - expenses + depreciation add-back - PITIA
      </p>

      <div className="income-form-grid">
        <IncomeFormField
          label="Property Address"
          required
          htmlFor="property_address"
          className="full-width"
        >
          <input
            id="property_address"
            aria-label="Rental property address"
            type="text"
            value={formData.property_address ?? ''}
            onChange={e => onChange('property_address', e.target.value)}
            placeholder="123 Main St, City, State 12345"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>Schedule E — Year 1</span>
      </div>

      <div className="income-form-grid four-col">
        <IncomeFormField label="Gross Rents (Line 3)" required htmlFor="gross_rents_line3">
          <input
            id="gross_rents_line3"
            aria-label="Annual gross rents from Line 3"
            type="number"
            min="0"
            value={formData.gross_rents_line3 ?? ''}
            onChange={e => onChange('gross_rents_line3', e.target.value)}
            placeholder="Annual gross rents"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Total Expenses (Line 20)" required htmlFor="total_expenses_line20">
          <input
            id="total_expenses_line20"
            aria-label="Total annual expenses from Line 20"
            type="number"
            min="0"
            value={formData.total_expenses_line20 ?? ''}
            onChange={e => onChange('total_expenses_line20', e.target.value)}
            placeholder="Annual expenses"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Depreciation (Line 18)" htmlFor="depreciation_line18">
          <input
            id="depreciation_line18"
            aria-label="Depreciation add-back from Line 18"
            type="number"
            min="0"
            value={formData.depreciation_line18 ?? ''}
            onChange={e => onChange('depreciation_line18', e.target.value)}
            placeholder="Add-back amount"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Amortization/Casualty (Line 19)" htmlFor="amortization_casualty_line19">
          <input
            id="amortization_casualty_line19"
            aria-label="Amortization and casualty loss from Line 19"
            type="number"
            min="0"
            value={formData.amortization_casualty_line19 ?? ''}
            onChange={e => onChange('amortization_casualty_line19', e.target.value)}
            placeholder="Add-back amount"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      <div className="income-form-divider">
        <span>PITIA (Monthly)</span>
      </div>

      <div className="income-form-grid four-col">
        <IncomeFormField label="Insurance" htmlFor="monthly_insurance">
          <input
            id="monthly_insurance"
            aria-label="Monthly insurance payment"
            type="number"
            min="0"
            value={formData.monthly_insurance ?? ''}
            onChange={e => onChange('monthly_insurance', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Mortgage Interest" htmlFor="monthly_mortgage_interest">
          <input
            id="monthly_mortgage_interest"
            aria-label="Monthly mortgage interest payment"
            type="number"
            min="0"
            value={formData.monthly_mortgage_interest ?? ''}
            onChange={e => onChange('monthly_mortgage_interest', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="Taxes" htmlFor="monthly_taxes">
          <input
            id="monthly_taxes"
            aria-label="Monthly tax payment"
            type="number"
            min="0"
            value={formData.monthly_taxes ?? ''}
            onChange={e => onChange('monthly_taxes', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>

        <IncomeFormField label="HOA" htmlFor="monthly_hoa">
          <input
            id="monthly_hoa"
            aria-label="Monthly HOA payment"
            type="number"
            min="0"
            value={formData.monthly_hoa ?? ''}
            onChange={e => onChange('monthly_hoa', e.target.value)}
            placeholder="0"
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      {/* Year 2 toggle */}
      <div style={{ marginTop: 20 }}>
        <IncomeFormField label="Include Year 2 Data" htmlFor="show_year2" checkbox>
          <input
            id="show_year2"
            aria-label="Show year 2 Schedule E fields"
            type="checkbox"
            checked={showYear2}
            onChange={e => setShowYear2(e.target.checked)}
            disabled={disabled}
          />
        </IncomeFormField>
      </div>

      {showYear2 && (
        <>
          <div className="income-form-divider">
            <span>Schedule E — Year 2</span>
          </div>

          <div className="income-form-grid four-col">
            <IncomeFormField label="Gross Rents Y2 (Line 3)" htmlFor="gross_rents_line3_y2">
              <input
                id="gross_rents_line3_y2"
                aria-label="Year 2 annual gross rents"
                type="number"
                min="0"
                value={formData.gross_rents_line3_y2 ?? ''}
                onChange={e => onChange('gross_rents_line3_y2', e.target.value)}
                placeholder="Annual gross rents"
                disabled={disabled}
              />
            </IncomeFormField>

            <IncomeFormField label="Total Expenses Y2 (Line 20)" htmlFor="total_expenses_line20_y2">
              <input
                id="total_expenses_line20_y2"
                aria-label="Year 2 total annual expenses"
                type="number"
                min="0"
                value={formData.total_expenses_line20_y2 ?? ''}
                onChange={e => onChange('total_expenses_line20_y2', e.target.value)}
                placeholder="Annual expenses"
                disabled={disabled}
              />
            </IncomeFormField>

            <IncomeFormField label="Depreciation Y2 (Line 18)" htmlFor="depreciation_line18_y2">
              <input
                id="depreciation_line18_y2"
                aria-label="Year 2 depreciation add-back"
                type="number"
                min="0"
                value={formData.depreciation_line18_y2 ?? ''}
                onChange={e => onChange('depreciation_line18_y2', e.target.value)}
                placeholder="Add-back amount"
                disabled={disabled}
              />
            </IncomeFormField>

            <IncomeFormField label="Amortization Y2 (Line 19)" htmlFor="amortization_casualty_line19_y2">
              <input
                id="amortization_casualty_line19_y2"
                aria-label="Year 2 amortization and casualty loss"
                type="number"
                min="0"
                value={formData.amortization_casualty_line19_y2 ?? ''}
                onChange={e => onChange('amortization_casualty_line19_y2', e.target.value)}
                placeholder="Add-back amount"
                disabled={disabled}
              />
            </IncomeFormField>
          </div>
        </>
      )}
    </div>
  );
}
