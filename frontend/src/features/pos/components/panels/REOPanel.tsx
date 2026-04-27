import React from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  SelectField,
  TextField,
  YesNoField,
  usePanelData,
} from './_shared';

interface Property {
  address?: string;
  property_type?: string;
  market_value?: number | null;
  monthly_payment?: number | null;
  monthly_rental_income?: number | null;
  status?: 'retain' | 'sell_pending' | 'sold';
}

export const REOPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  const ownsProperty = data.owns_other_property as boolean | null | undefined;
  const properties: Property[] = (data.properties as Property[]) || [{}];

  const update = (idx: number, key: keyof Property, value: unknown) => {
    const next = properties.map((p, i) => (i === idx ? { ...p, [key]: value } : p));
    updateField('properties', next);
  };
  const add = () => updateField('properties', [...properties, {}]);

  return (
    <>
      <FormSection title="Real estate you own">
        <YesNoField label="Do you currently own any real estate?"
          name="owns_other_property" value={ownsProperty as boolean | null}
          onChange={updateField} cols={3} />
      </FormSection>

      {ownsProperty === true && (
        <FormSection title="Property details"
          description="List every property you currently own, including the one you're selling.">
          {properties.map((prop, idx) => (
            <div key={idx} className="urla-subform" style={{ gridColumn: '1 / -1' }}>
              <div className="urla-subform__header"><span>Property {idx + 1}</span></div>
              <div className="urla-form-grid">
                <TextField label="Address" name={`addr_${idx}`} required cols={3}
                  value={prop.address} onChange={(_, v) => update(idx, 'address', v)} />
                <SelectField label="Property type" name={`ptype_${idx}`} required cols={1}
                  options={[
                    { value: 'sfr', label: 'Single-family' },
                    { value: 'condo', label: 'Condo' },
                    { value: 'townhouse', label: 'Townhouse' },
                    { value: 'multi_2_4', label: '2-4 units' },
                    { value: 'land', label: 'Land' },
                  ]}
                  value={prop.property_type} onChange={(_, v) => update(idx, 'property_type', v)} />
                <TextField label="Market value" name={`mv_${idx}`} type="currency" cols={1}
                  value={prop.market_value} onChange={(_, v) => update(idx, 'market_value', v)} />
                <TextField label="Monthly payment (P&I+T+I)" name={`mp_${idx}`} type="currency" cols={1}
                  value={prop.monthly_payment}
                  onChange={(_, v) => update(idx, 'monthly_payment', v)} />
                <TextField label="Monthly rental income" name={`mri_${idx}`} type="currency" cols={1}
                  value={prop.monthly_rental_income}
                  onChange={(_, v) => update(idx, 'monthly_rental_income', v)} />
                <SelectField label="Status" name={`status_${idx}`} required cols={2}
                  options={[
                    { value: 'retain', label: 'Will retain' },
                    { value: 'sell_pending', label: 'Selling — pending close' },
                    { value: 'sold', label: 'Sold' },
                  ]}
                  value={prop.status} onChange={(_, v) => update(idx, 'status', v)} />
              </div>
            </div>
          ))}
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="button" className="urla-link-btn" onClick={add}>+ Add another property</button>
          </div>
        </FormSection>
      )}

      <ContinueButton onClick={onComplete} />
    </>
  );
};
