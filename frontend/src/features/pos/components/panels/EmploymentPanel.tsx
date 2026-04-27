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

export const EmploymentPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  return (
    <>
      <FormSection title="Current employment">
        <SelectField label="Employment type" name="employment_type" required
          options={[
            { value: 'employee', label: 'W-2 Employee' },
            { value: 'self_employed', label: 'Self-employed' },
            { value: 'contractor', label: '1099 Contractor' },
            { value: 'retired', label: 'Retired' },
            { value: 'military', label: 'Military' },
            { value: 'other', label: 'Other' },
          ]}
          value={data.employment_type} onChange={updateField} cols={1} />
        <TextField label="Years in profession" name="years_in_profession" type="number"
          value={data.years_in_profession} onChange={updateField} cols={1} />
      </FormSection>

      <FormSection title="Employer">
        <TextField label="Employer name" name="employer.name" required cols={2}
          value={(data.employer as any)?.name} onChange={updateField} />
        <TextField label="Position / Job title" name="employer.position" required cols={1}
          value={(data.employer as any)?.position} onChange={updateField} />

        <TextField label="Start date" name="employer.start_date" type="date" required cols={1}
          value={(data.employer as any)?.start_date} onChange={updateField} />
        <TextField label="Employer phone" name="employer.phone" type="tel" cols={1}
          value={(data.employer as any)?.phone} onChange={updateField} />
        <YesNoField label="Self-employed?" name="employer.is_self_employed"
          value={(data.employer as any)?.is_self_employed} onChange={updateField} />

        <TextField label="Address" name="employer.street" cols={3}
          value={(data.employer as any)?.street} onChange={updateField} />
        <TextField label="City" name="employer.city" cols={1}
          value={(data.employer as any)?.city} onChange={updateField} />
        <TextField label="State" name="employer.state" cols={1}
          value={(data.employer as any)?.state} onChange={updateField} />
        <TextField label="ZIP" name="employer.zip" cols={1}
          value={(data.employer as any)?.zip} onChange={updateField} />
      </FormSection>

      <FormSection title="Monthly income"
        description="Enter gross monthly amounts before taxes.">
        <TextField label="Base income" name="income.base" type="currency" required cols={1}
          value={(data.income as any)?.base} onChange={updateField} />
        <TextField label="Overtime" name="income.overtime" type="currency"
          value={(data.income as any)?.overtime} onChange={updateField} />
        <TextField label="Bonus" name="income.bonus" type="currency"
          value={(data.income as any)?.bonus} onChange={updateField} />
        <TextField label="Commission" name="income.commission" type="currency"
          value={(data.income as any)?.commission} onChange={updateField} />
        <TextField label="Other (military allowances, etc.)" name="income.other" type="currency"
          value={(data.income as any)?.other} onChange={updateField} cols={2} />
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
