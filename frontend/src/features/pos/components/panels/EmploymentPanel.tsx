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

interface EmployerEntry {
  name?: string;
  position?: string;
  start_date?: string;
  end_date?: string;
  phone?: string;
  is_self_employed?: boolean;
  street?: string;
  city?: string;
  state?: string;
  zip?: string;
  income_base?: number;
  income_overtime?: number;
  income_bonus?: number;
  income_commission?: number;
  income_other?: number;
}

const EMPTY_EMPLOYER: EmployerEntry = {};

export const EmploymentPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  const additionalEmployers = (data.additional_employers as EmployerEntry[]) || [];

  const updateAdditional = (idx: number, field: string, value: unknown) => {
    const updated = [...additionalEmployers];
    updated[idx] = { ...updated[idx], [field]: value };
    onChange({ ...data, additional_employers: updated });
  };

  const addEmployer = () => {
    onChange({ ...data, additional_employers: [...additionalEmployers, { ...EMPTY_EMPLOYER }] });
  };

  const removeEmployer = (idx: number) => {
    const updated = additionalEmployers.filter((_, i) => i !== idx);
    onChange({ ...data, additional_employers: updated });
  };

  return (
    <>
      <p className="urla-form-section__desc">
        Provide your current employment and any previous jobs within the past 2 years.
        If you've had multiple positions, use "Add another employer" below.
      </p>

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

        <TextField label="Address" name="employer.street" cols={2}
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

      {additionalEmployers.map((emp, idx) => (
        <React.Fragment key={idx}>
          <FormSection title={`Previous employer ${additionalEmployers.length > 1 ? `#${idx + 1}` : ''}`}>
            <TextField label="Employer name" name={`emp_${idx}_name`} cols={2}
              value={emp.name} onChange={(_, v) => updateAdditional(idx, 'name', v)} />
            <TextField label="Position" name={`emp_${idx}_position`} cols={1}
              value={emp.position} onChange={(_, v) => updateAdditional(idx, 'position', v)} />
            <TextField label="Start date" name={`emp_${idx}_start`} type="date" cols={1}
              value={emp.start_date} onChange={(_, v) => updateAdditional(idx, 'start_date', v)} />

            <TextField label="End date" name={`emp_${idx}_end`} type="date" cols={1}
              value={emp.end_date} onChange={(_, v) => updateAdditional(idx, 'end_date', v)} />
            <TextField label="Phone" name={`emp_${idx}_phone`} type="tel" cols={1}
              value={emp.phone} onChange={(_, v) => updateAdditional(idx, 'phone', v)} />
            <YesNoField label="Self-employed?" name={`emp_${idx}_self`}
              value={emp.is_self_employed} onChange={(_, v) => updateAdditional(idx, 'is_self_employed', v)} />

            <TextField label="Address" name={`emp_${idx}_street`} cols={2}
              value={emp.street} onChange={(_, v) => updateAdditional(idx, 'street', v)} />
            <TextField label="City" name={`emp_${idx}_city`} cols={1}
              value={emp.city} onChange={(_, v) => updateAdditional(idx, 'city', v)} />
            <TextField label="State" name={`emp_${idx}_state`} cols={1}
              value={emp.state} onChange={(_, v) => updateAdditional(idx, 'state', v)} />
            <TextField label="ZIP" name={`emp_${idx}_zip`} cols={1}
              value={emp.zip} onChange={(_, v) => updateAdditional(idx, 'zip', v)} />
          </FormSection>

          <FormSection title={`Income — ${emp.name || 'Previous employer'}`}
            description="Gross monthly income from this position.">
            <TextField label="Base" name={`emp_${idx}_inc_base`} type="currency" cols={1}
              value={emp.income_base} onChange={(_, v) => updateAdditional(idx, 'income_base', v)} />
            <TextField label="Overtime" name={`emp_${idx}_inc_ot`} type="currency"
              value={emp.income_overtime} onChange={(_, v) => updateAdditional(idx, 'income_overtime', v)} />
            <TextField label="Bonus" name={`emp_${idx}_inc_bonus`} type="currency"
              value={emp.income_bonus} onChange={(_, v) => updateAdditional(idx, 'income_bonus', v)} />
            <TextField label="Commission" name={`emp_${idx}_inc_comm`} type="currency"
              value={emp.income_commission} onChange={(_, v) => updateAdditional(idx, 'income_commission', v)} />

            <div className="urla-field urla-field--cols-4">
              <button type="button" className="urla-btn-link urla-btn-link--danger" onClick={() => removeEmployer(idx)}>
                Remove this employer
              </button>
            </div>
          </FormSection>
        </React.Fragment>
      ))}

      <div className="urla-add-entry">
        <button type="button" className="urla-btn-link" onClick={addEmployer}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Add another employer
        </button>
      </div>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
