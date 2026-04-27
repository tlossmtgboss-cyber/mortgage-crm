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

export const ResidencePanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  return (
    <>
      <FormSection title="Where do you currently live?">
        <TextField label="Street address" name="current.street" required cols={3}
          value={(data.current as any)?.street} onChange={updateField} />
        <TextField label="Unit / Apt" name="current.unit"
          value={(data.current as any)?.unit} onChange={updateField} />
        <TextField label="City" name="current.city" required cols={2}
          value={(data.current as any)?.city} onChange={updateField} />
        <SelectField label="State" name="current.state" required
          options={STATE_OPTIONS}
          value={(data.current as any)?.state} onChange={updateField} />
        <TextField label="ZIP code" name="current.zip" required
          value={(data.current as any)?.zip} onChange={updateField} inputMode="numeric" />

        <SelectField label="Housing situation" name="current.housing_status" required
          options={[
            { value: 'own', label: 'I own this home' },
            { value: 'rent', label: 'I rent' },
            { value: 'no_charge', label: 'Living rent-free' },
          ]}
          value={(data.current as any)?.housing_status} onChange={updateField} />
        <TextField label="Years at this address" name="current.years_at_address"
          type="number" required cols={1}
          value={(data.current as any)?.years_at_address} onChange={updateField} />
        <TextField label="Months at this address" name="current.months_at_address"
          type="number" cols={1}
          value={(data.current as any)?.months_at_address} onChange={updateField} />

        <TextField label="Monthly housing cost"
          name="current.monthly_cost" type="currency" required cols={1}
          helpText="Rent or mortgage P&I"
          value={(data.current as any)?.monthly_cost} onChange={updateField} />
      </FormSection>

      <FormSection
        title="Previous address (if less than 2 years here)"
        description="Lenders need a 24-month address history. Skip if you've been at your current address for 2+ years."
      >
        <TextField label="Street address" name="previous.street" cols={3}
          value={(data.previous as any)?.street} onChange={updateField} />
        <TextField label="City" name="previous.city" cols={2}
          value={(data.previous as any)?.city} onChange={updateField} />
        <SelectField label="State" name="previous.state" options={STATE_OPTIONS}
          value={(data.previous as any)?.state} onChange={updateField} />
        <TextField label="ZIP" name="previous.zip"
          value={(data.previous as any)?.zip} onChange={updateField} />
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
