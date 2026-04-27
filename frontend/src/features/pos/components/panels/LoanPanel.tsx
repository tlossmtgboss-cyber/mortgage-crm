import React from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  SelectField,
  TextField,
  usePanelData,
} from './_shared';

export const LoanPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  return (
    <>
      <FormSection title="What kind of loan are you applying for?">
        <SelectField label="Loan purpose" name="loan_purpose" required
          options={[
            { value: 'purchase', label: 'Purchase' },
            { value: 'refinance', label: 'Refinance' },
            { value: 'cash_out_refi', label: 'Cash-out refinance' },
            { value: 'construction', label: 'Construction' },
          ]}
          value={data.loan_purpose} onChange={updateField} cols={1} />
        <SelectField label="Loan type" name="loan_type" required
          options={[
            { value: 'conventional', label: 'Conventional' },
            { value: 'fha', label: 'FHA' },
            { value: 'va', label: 'VA' },
            { value: 'usda', label: 'USDA' },
            { value: 'jumbo', label: 'Jumbo' },
          ]}
          value={data.loan_type} onChange={updateField} cols={1} />
        <TextField label="Requested loan amount" name="loan_amount"
          type="currency" required cols={1}
          value={data.loan_amount} onChange={updateField} />
      </FormSection>

      <FormSection title="The property">
        <TextField label="Property address" name="property.address" required cols={3}
          value={(data.property as any)?.address} onChange={updateField} />
        <SelectField label="Property type" name="property.type" required cols={1}
          options={[
            { value: 'sfr', label: 'Single-family' },
            { value: 'condo', label: 'Condo' },
            { value: 'townhouse', label: 'Townhouse' },
            { value: 'multi_2_4', label: '2-4 units' },
            { value: 'manufactured', label: 'Manufactured home' },
          ]}
          value={(data.property as any)?.type} onChange={updateField} />
        <SelectField label="Occupancy" name="property.occupancy" required cols={1}
          options={[
            { value: 'primary', label: 'Primary residence' },
            { value: 'second_home', label: 'Second home' },
            { value: 'investment', label: 'Investment property' },
          ]}
          value={(data.property as any)?.occupancy} onChange={updateField} />
        <TextField label="Estimated value / Purchase price" name="property.value"
          type="currency" required cols={1}
          value={(data.property as any)?.value} onChange={updateField} />
        <TextField label="Year built" name="property.year_built" type="number" cols={1}
          value={(data.property as any)?.year_built} onChange={updateField} />
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
