import React from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  SelectField,
  TextField,
  usePanelData,
} from './_shared';

const STATE_OPTIONS = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN',
  'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
  'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI',
  'WY', 'DC'].map(s => ({ value: s, label: s }));

interface AddressEntry {
  street?: string;
  unit?: string;
  city?: string;
  state?: string;
  zip?: string;
  housing_status?: string;
  years_at_address?: number;
  months_at_address?: number;
  monthly_cost?: number;
}

const EMPTY_ADDRESS: AddressEntry = {};

export const ResidencePanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  const currentAddr = (data.current as AddressEntry) || {};
  const additionalAddresses = (data.additional_addresses as AddressEntry[]) || [];

  const updateAdditional = (idx: number, field: string, value: unknown) => {
    const updated = [...additionalAddresses];
    updated[idx] = { ...updated[idx], [field]: value };
    onChange({ ...data, additional_addresses: updated });
  };

  const addAddress = () => {
    onChange({ ...data, additional_addresses: [...additionalAddresses, { ...EMPTY_ADDRESS }] });
  };

  const removeAddress = (idx: number) => {
    const updated = additionalAddresses.filter((_, i) => i !== idx);
    onChange({ ...data, additional_addresses: updated });
  };

  const currentYears = Number(currentAddr.years_at_address) || 0;
  const currentMonths = Number(currentAddr.months_at_address) || 0;
  const totalMonthsAtCurrent = currentYears * 12 + currentMonths;
  const needsMore = totalMonthsAtCurrent < 24;

  return (
    <>
      <p className="urla-form-section__desc">
        Lenders require a full 24-month address history. If you've been at your current
        address less than 2 years, add your previous address(es) below.
      </p>

      <FormSection title="Current address">
        <TextField label="Street address" name="current.street" required cols={3}
          value={currentAddr.street} onChange={updateField} />
        <TextField label="Unit / Apt" name="current.unit"
          value={currentAddr.unit} onChange={updateField} />
        <TextField label="City" name="current.city" required cols={2}
          value={currentAddr.city} onChange={updateField} />
        <SelectField label="State" name="current.state" required
          options={STATE_OPTIONS}
          value={currentAddr.state} onChange={updateField} />
        <TextField label="ZIP code" name="current.zip" required
          value={currentAddr.zip} onChange={updateField} inputMode="numeric" />

        <SelectField label="Housing situation" name="current.housing_status" required
          options={[
            { value: 'own', label: 'I own this home' },
            { value: 'rent', label: 'I rent' },
            { value: 'no_charge', label: 'Living rent-free' },
          ]}
          value={currentAddr.housing_status} onChange={updateField} />
        <TextField label="Years at this address" name="current.years_at_address"
          type="number" required cols={1}
          value={currentAddr.years_at_address} onChange={updateField} />
        <TextField label="Months" name="current.months_at_address"
          type="number" cols={1}
          value={currentAddr.months_at_address} onChange={updateField} />
        <TextField label="Monthly housing cost"
          name="current.monthly_cost" type="currency" required cols={1}
          helpText="Rent or mortgage P&I"
          value={currentAddr.monthly_cost} onChange={updateField} />
      </FormSection>

      {needsMore && additionalAddresses.length === 0 && (
        <div className="urla-banner urla-banner--info">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <p>
            <strong>More history needed.</strong> You've been at your current address less than 2 years.
            Please add your previous address(es) to cover a full 24-month history.
          </p>
        </div>
      )}

      {additionalAddresses.map((addr, idx) => (
        <FormSection
          key={idx}
          title={`Previous address ${additionalAddresses.length > 1 ? `#${idx + 1}` : ''}`}
        >
          <TextField label="Street address" name={`addr_${idx}_street`} cols={3}
            value={addr.street} onChange={(_, v) => updateAdditional(idx, 'street', v)} />
          <TextField label="Unit / Apt" name={`addr_${idx}_unit`}
            value={addr.unit} onChange={(_, v) => updateAdditional(idx, 'unit', v)} />
          <TextField label="City" name={`addr_${idx}_city`} cols={2}
            value={addr.city} onChange={(_, v) => updateAdditional(idx, 'city', v)} />
          <SelectField label="State" name={`addr_${idx}_state`} options={STATE_OPTIONS}
            value={addr.state} onChange={(_, v) => updateAdditional(idx, 'state', v)} />
          <TextField label="ZIP" name={`addr_${idx}_zip`}
            value={addr.zip} onChange={(_, v) => updateAdditional(idx, 'zip', v)} inputMode="numeric" />

          <SelectField label="Housing" name={`addr_${idx}_housing`}
            options={[
              { value: 'own', label: 'Owned' },
              { value: 'rent', label: 'Rented' },
              { value: 'no_charge', label: 'Rent-free' },
            ]}
            value={addr.housing_status} onChange={(_, v) => updateAdditional(idx, 'housing_status', v)} />
          <TextField label="Years there" name={`addr_${idx}_years`} type="number" cols={1}
            value={addr.years_at_address} onChange={(_, v) => updateAdditional(idx, 'years_at_address', v)} />
          <TextField label="Months" name={`addr_${idx}_months`} type="number" cols={1}
            value={addr.months_at_address} onChange={(_, v) => updateAdditional(idx, 'months_at_address', v)} />

          <div className="urla-field urla-field--cols-4">
            <button type="button" className="urla-btn-link urla-btn-link--danger" onClick={() => removeAddress(idx)}>
              Remove this address
            </button>
          </div>
        </FormSection>
      ))}

      <div className="urla-add-entry">
        <button type="button" className="urla-btn-link" onClick={addAddress}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Add another address
        </button>
      </div>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
