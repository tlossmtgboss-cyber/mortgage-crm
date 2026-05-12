import React, { useMemo, useRef } from 'react';

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

const PROPERTY_TYPE_OPTIONS = [
  { value: 'sfr', label: 'Single-family' },
  { value: 'condo', label: 'Condo' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'multi_2_4', label: '2-4 units' },
  { value: 'manufactured', label: 'Manufactured home' },
];

const OCCUPANCY_OPTIONS = [
  { value: 'primary', label: 'Primary residence' },
  { value: 'second_home', label: 'Second home' },
  { value: 'investment', label: 'Investment property' },
];

export const LoanPanel: React.FC<PanelProps> = ({ section, onChange, onComplete, intakeLoanPurpose }) => {
  const { data, updateField } = usePanelData(section, onChange);

  const loanPurpose = intakeLoanPurpose || (data.loan_purpose as string) || '';
  const property = (data.property as Record<string, unknown>) || {};

  // Refs to hold latest values, avoiding stale closures in the effect below.
  const dataRef = useRef(data);
  dataRef.current = data;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Sync intake loan_purpose into section data so the backend has it.
  React.useEffect(() => {
    if (intakeLoanPurpose && dataRef.current.loan_purpose !== intakeLoanPurpose) {
      onChangeRef.current({ ...dataRef.current, loan_purpose: intakeLoanPurpose });
    }
  }, [intakeLoanPurpose]);

  const purchasePrice = Number(data.purchase_price) || 0;
  const loanAmount = Number(data.loan_amount) || 0;
  const downPayment = useMemo(() => {
    if (purchasePrice > 0 && loanAmount > 0 && loanAmount <= purchasePrice) {
      return purchasePrice - loanAmount;
    }
    return null;
  }, [purchasePrice, loanAmount]);

  const downPaymentPct = useMemo(() => {
    if (downPayment !== null && purchasePrice > 0) {
      return ((downPayment / purchasePrice) * 100).toFixed(1);
    }
    return null;
  }, [downPayment, purchasePrice]);

  return (
    <>
      {loanPurpose === 'purchase' && (
        <>
          <FormSection title="Loan details">
            <TextField label="Purchase price" name="purchase_price" type="currency" required cols={1}
              value={data.purchase_price} onChange={updateField} />
            <TextField label="Loan amount" name="loan_amount" type="currency" required cols={1}
              value={data.loan_amount} onChange={updateField} />
            <div className="urla-field urla-field--cols-2">
              <label className="urla-field__label">Down payment</label>
              <div className="urla-computed-value">
                {downPayment !== null
                  ? `$${downPayment.toLocaleString()} (${downPaymentPct}%)`
                  : '—'}
              </div>
            </div>
          </FormSection>

          <FormSection title="Subject property" description="Don't have an address yet? No problem — just tell us the area you're looking in.">
            <SelectField label="Property type" name="property.type" required cols={1}
              options={PROPERTY_TYPE_OPTIONS}
              value={property.type} onChange={updateField} />
            <SelectField label="Occupancy" name="property.occupancy" required cols={1}
              options={OCCUPANCY_OPTIONS}
              value={property.occupancy} onChange={updateField} />
            <TextField label="City" name="property.city" cols={1}
              value={property.city} onChange={updateField} />
            <SelectField label="State" name="property.state" cols={1}
              options={STATE_OPTIONS}
              value={property.state} onChange={updateField} />
            <TextField label="ZIP code" name="property.zip" cols={1}
              value={property.zip} onChange={updateField} inputMode="numeric" />
          </FormSection>
        </>
      )}

      {loanPurpose === 'refinance' && (
        <>
          <FormSection title="Refinance details">
            <SelectField label="Refinance type" name="refinance_type" required cols={1}
              options={[
                { value: 'rate_term', label: 'Rate & term' },
                { value: 'cash_out', label: 'Cash-out' },
              ]}
              value={data.refinance_type} onChange={updateField} />
            <TextField label="Requested loan amount" name="loan_amount" type="currency" required cols={1}
              value={data.loan_amount} onChange={updateField} />
          </FormSection>

          <FormSection title="Subject property">
            <TextField label="Property address" name="property.address" required cols={3}
              value={property.address} onChange={updateField} />
            <TextField label="City" name="property.city" required cols={1}
              value={property.city} onChange={updateField} />
            <SelectField label="State" name="property.state" required cols={1}
              options={STATE_OPTIONS}
              value={property.state} onChange={updateField} />
            <TextField label="ZIP code" name="property.zip" required cols={1}
              value={property.zip} onChange={updateField} inputMode="numeric" />
            <SelectField label="Property type" name="property.type" required cols={1}
              options={PROPERTY_TYPE_OPTIONS}
              value={property.type} onChange={updateField} />
            <SelectField label="Occupancy" name="property.occupancy" required cols={1}
              options={OCCUPANCY_OPTIONS}
              value={property.occupancy} onChange={updateField} />
            <TextField label="Estimated value" name="property.value" type="currency" required cols={1}
              value={property.value} onChange={updateField} />
          </FormSection>
        </>
      )}

      <ContinueButton onClick={onComplete} />
    </>
  );
};
