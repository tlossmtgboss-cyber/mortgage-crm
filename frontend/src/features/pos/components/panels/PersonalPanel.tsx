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

  const citizenship = (data.citizenship as string) || '';

  return (
    <>
      <p className="urla-form-section__desc">
        Tell us a bit about yourself. This information is used to verify your identity and pull credit when you're ready.
      </p>

      <FormSection>
        <TextField label="First name" name="first_name" required value={data.first_name} onChange={updateField} />
        <TextField label="Middle" name="middle_name" value={data.middle_name} onChange={updateField} />
        <TextField label="Last name" name="last_name" required value={data.last_name} onChange={updateField} />
        <SelectField
          label="Suffix"
          name="suffix"
          value={data.suffix}
          onChange={updateField}
          options={[
            { value: 'Jr', label: 'Jr.' },
            { value: 'Sr', label: 'Sr.' },
            { value: 'II', label: 'II' },
            { value: 'III', label: 'III' },
          ]}
        />
      </FormSection>

      <FormSection>
        <TextField label="Date of birth" name="_dob" type="date" required value={dob} onChange={(_, v) => setDOB(v as string)}
          helpText={application?.has_dob ? 'Already on file — leave blank to keep' : undefined} />
        <TextField label="Social Security #" name="_ssn" required value={ssn} placeholder="•••-••-XXXX"
          onChange={(_, v) => setSSN(v as string)} inputMode="numeric"
          helpText={application?.has_ssn ? 'Already on file — leave blank to keep' : undefined} />
        <SelectField label="Marital status" name="marital_status" required value={data.marital_status} onChange={updateField} options={[
          { value: 'married', label: 'Married' },
          { value: 'single', label: 'Single' },
          { value: 'separated', label: 'Separated' },
          { value: 'unmarried', label: 'Unmarried (widowed/divorced)' },
        ]} />
      </FormSection>

      <FormSection title="Citizenship">
        <div className="urla-field urla-field--cols-4">
          <div className="urla-radio-cards">
            {[
              { value: 'us_citizen', label: 'U.S. Citizen', desc: 'Born or naturalized' },
              { value: 'permanent_resident', label: 'Permanent Resident', desc: 'Hold a green card' },
              { value: 'non_permanent_resident', label: 'Non-Permanent Resident', desc: 'Visa or other status' },
            ].map(opt => (
              <label key={opt.value} className={`urla-radio-card${citizenship === opt.value ? ' is-selected' : ''}`}>
                <input type="radio" name="citizenship" value={opt.value} checked={citizenship === opt.value}
                  onChange={() => updateField('citizenship', opt.value)} className="urla-radio-card__input" />
                <span className="urla-radio-card__dot" />
                <span className="urla-radio-card__text">
                  <span className="urla-radio-card__label">{opt.label}</span>
                  <span className="urla-radio-card__desc">{opt.desc}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </FormSection>

      <FormSection title="Dependents">
        <TextField label="Number of dependents" name="dependents_count" type="number" value={data.dependents_count} onChange={updateField} cols={2} />
        <TextField label="Ages (comma separated)" name="dependents_ages" value={data.dependents_ages} onChange={updateField} cols={2}
          placeholder="e.g. 14, 11" />
      </FormSection>

      <div className="urla-banner">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        <p>
          <strong>A note on your SSN.</strong> Your number is encrypted with AES-256 the moment you type it.
          We only use it to verify your identity and pull credit when you authorize.
        </p>
      </div>

      <ContinueButton onClick={handleContinue} />
    </>
  );
};
