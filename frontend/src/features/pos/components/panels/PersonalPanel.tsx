import React, { useState } from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  SelectField,
  TextField,
  usePanelData,
} from './_shared';
import type { SectionUpdateRequest } from '../../types';
import { posApi } from '../../api';

export const PersonalPanel: React.FC<PanelProps> = ({
  section,
  onChange,
  onComplete,
  application,
}) => {
  const { data, updateField } = usePanelData(section, onChange);

  // Sensitive fields are not echoed back from the server, so we keep them in
  // local state and PATCH them on save with mark_complete=true.
  const [ssn, setSSN] = useState('');
  const [dob, setDOB] = useState('');

  const handleContinue = async () => {
    if (!application) return;
    const body: SectionUpdateRequest = {
      data,
      mark_complete: true,
    };
    if (ssn) body.ssn = ssn;
    if (dob) body.dob = dob;
    await posApi.updateSection(application.id, 'personal', body);
    onComplete();
  };

  return (
    <>
      <FormSection title="Tell us about yourself">
        <TextField
          label="First name"
          name="first_name"
          required
          value={data.first_name}
          onChange={updateField}
          cols={1}
        />
        <TextField
          label="Middle name"
          name="middle_name"
          value={data.middle_name}
          onChange={updateField}
          cols={1}
        />
        <TextField
          label="Last name"
          name="last_name"
          required
          value={data.last_name}
          onChange={updateField}
          cols={1}
        />
        <SelectField
          label="Suffix"
          name="suffix"
          value={data.suffix}
          onChange={updateField}
          cols={1}
          options={[
            { value: 'Jr', label: 'Jr.' },
            { value: 'Sr', label: 'Sr.' },
            { value: 'II', label: 'II' },
            { value: 'III', label: 'III' },
          ]}
        />
      </FormSection>

      <FormSection title="Contact info">
        <TextField
          label="Email"
          name="email"
          type="email"
          required
          value={data.email}
          onChange={updateField}
          cols={1}
        />
        <TextField
          label="Phone"
          name="phone"
          type="tel"
          required
          value={data.phone}
          onChange={updateField}
          cols={1}
        />
      </FormSection>

      <FormSection
        title="Identity"
        description="This information is encrypted at rest and never shared without your consent."
      >
        <TextField
          label="Social Security Number"
          name="_ssn"
          required
          value={ssn}
          placeholder="XXX-XX-XXXX"
          onChange={(_, v) => setSSN(v as string)}
          inputMode="numeric"
          helpText={application?.has_ssn ? 'Already on file — leave blank to keep' : undefined}
          cols={1}
        />
        <TextField
          label="Date of birth"
          name="_dob"
          type="date"
          required
          value={dob}
          onChange={(_, v) => setDOB(v as string)}
          helpText={application?.has_dob ? 'Already on file — leave blank to keep' : undefined}
          cols={1}
        />
      </FormSection>

      <FormSection title="Marital status & dependents">
        <SelectField
          label="Marital status"
          name="marital_status"
          required
          value={data.marital_status}
          onChange={updateField}
          cols={1}
          options={[
            { value: 'married', label: 'Married' },
            { value: 'single', label: 'Single' },
            { value: 'separated', label: 'Separated' },
            { value: 'unmarried', label: 'Unmarried (widowed/divorced)' },
          ]}
        />
        <TextField
          label="Number of dependents"
          name="dependents_count"
          type="number"
          value={data.dependents_count}
          onChange={updateField}
          cols={1}
        />
      </FormSection>

      <ContinueButton onClick={handleContinue} />
    </>
  );
};
