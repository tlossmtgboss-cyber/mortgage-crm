import React, { useState } from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  SelectField,
  TextField,
  YesNoField,
  usePanelData,
} from './_shared';
import type { SectionUpdateRequest } from '../../types';
import { posApi } from '../../api';

export const CoBorrowerPanel: React.FC<PanelProps> = ({
  section,
  onChange,
  onComplete,
  application,
}) => {
  const { data, updateField } = usePanelData(section, onChange);
  const [coSSN, setCoSSN] = useState('');
  const [coDOB, setCoDOB] = useState('');

  const hasCoBorrower = data.has_coborrower as boolean | null;

  const handleContinue = async () => {
    if (!application) return;
    const body: SectionUpdateRequest = { data, mark_complete: true };
    if (coSSN) body.co_ssn = coSSN;
    if (coDOB) body.co_dob = coDOB;
    await posApi.updateSection(application.id, 'coborrower', body);
    onComplete();
  };

  return (
    <>
      <p className="urla-form-section__desc">
        If someone is applying with you, enter their information below.
        A co-borrower's income and credit are considered jointly.
      </p>

      <FormSection>
        <YesNoField
          label="Will anyone else be on the loan with you?"
          name="has_coborrower"
          value={hasCoBorrower}
          onChange={updateField}
          cols={2}
        />
      </FormSection>

      {hasCoBorrower === true && (
        <>
          <FormSection title="Co-Borrower Identity">
            <TextField label="First name" name="co_first_name" required value={data.co_first_name} onChange={updateField} />
            <TextField label="Middle" name="co_middle_name" value={data.co_middle_name} onChange={updateField} />
            <TextField label="Last name" name="co_last_name" required value={data.co_last_name} onChange={updateField} />
            <SelectField label="Suffix" name="co_suffix" value={data.co_suffix} onChange={updateField} options={[
              { value: 'Jr', label: 'Jr.' },
              { value: 'Sr', label: 'Sr.' },
              { value: 'II', label: 'II' },
              { value: 'III', label: 'III' },
            ]} />
          </FormSection>

          <FormSection>
            <TextField label="Date of birth" name="_co_dob" type="date" required value={coDOB} onChange={(_, v) => setCoDOB(v as string)}
              helpText={(application as any)?.has_co_dob ? 'Already on file — leave blank to keep' : undefined} />
            <TextField label="Social Security #" name="_co_ssn" required value={coSSN} placeholder="•••-••-XXXX"
              onChange={(_, v) => setCoSSN(v as string)} inputMode="numeric"
              helpText={application?.has_co_ssn ? 'Already on file — leave blank to keep' : undefined} />
            <SelectField label="Marital status" name="co_marital_status" required value={data.co_marital_status} onChange={updateField} options={[
              { value: 'married', label: 'Married' },
              { value: 'single', label: 'Single' },
              { value: 'separated', label: 'Separated' },
              { value: 'unmarried', label: 'Unmarried (widowed/divorced)' },
            ]} />
          </FormSection>

          <FormSection title="Co-Borrower Contact">
            <TextField label="Email address" name="co_email" type="email" required value={data.co_email} onChange={updateField} cols={2} />
            <TextField label="Phone" name="co_phone" type="tel" value={data.co_phone} onChange={updateField} />
            <SelectField label="Relationship to borrower" name="co_relationship" value={data.co_relationship} onChange={updateField} options={[
              { value: 'spouse', label: 'Spouse' },
              { value: 'partner', label: 'Domestic Partner' },
              { value: 'parent', label: 'Parent' },
              { value: 'relative', label: 'Other Relative' },
              { value: 'non_relative', label: 'Non-Relative' },
            ]} />
          </FormSection>
        </>
      )}

      <ContinueButton
        onClick={handleContinue}
        disabled={hasCoBorrower === null}
        label={hasCoBorrower === false ? 'Skip & Continue' : 'Save & Continue'}
      />
    </>
  );
};
