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

interface Liability {
  type?: string;
  creditor?: string;
  balance?: number | null;
  monthly_payment?: number | null;
  pay_off_at_close?: boolean;
}

export const LiabilitiesPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);
  const liabilities: Liability[] = (data.liabilities as Liability[]) || [{}];

  const update = (idx: number, key: keyof Liability, value: unknown) => {
    const next = liabilities.map((l, i) => (i === idx ? { ...l, [key]: value } : l));
    updateField('liabilities', next);
  };
  const add = () => updateField('liabilities', [...liabilities, {}]);
  const remove = (idx: number) => {
    if (liabilities.length === 1) return;
    updateField('liabilities', liabilities.filter((_, i) => i !== idx));
  };

  return (
    <>
      <FormSection
        title="Monthly debts & obligations"
        description="Add credit cards, auto loans, student loans, child support, alimony, and other recurring obligations."
      >
        {liabilities.map((liab, idx) => (
          <div key={idx} className="urla-subform" style={{ gridColumn: '1 / -1' }}>
            <div className="urla-subform__header">
              <span>Debt {idx + 1}</span>
              {liabilities.length > 1 && (
                <button type="button" className="urla-btn-link urla-btn-link--danger" onClick={() => remove(idx)}>Remove</button>
              )}
            </div>
            <div className="urla-form-grid">
              <SelectField label="Type" name={`liab_type_${idx}`} required cols={1}
                options={[
                  { value: 'credit_card', label: 'Credit card' },
                  { value: 'auto_loan', label: 'Auto loan' },
                  { value: 'student_loan', label: 'Student loan' },
                  { value: 'personal_loan', label: 'Personal loan' },
                  { value: 'child_support', label: 'Child support' },
                  { value: 'alimony', label: 'Alimony' },
                  { value: 'tax_lien', label: 'Tax lien' },
                  { value: 'other', label: 'Other' },
                ]}
                value={liab.type} onChange={(_, v) => update(idx, 'type', v)} />
              <TextField label="Creditor" name={`creditor_${idx}`} required cols={1}
                value={liab.creditor} onChange={(_, v) => update(idx, 'creditor', v)} />
              <TextField label="Balance" name={`bal_${idx}`} type="currency" cols={1}
                value={liab.balance} onChange={(_, v) => update(idx, 'balance', v)} />
              <TextField label="Monthly payment" name={`pmt_${idx}`} type="currency" required cols={1}
                value={liab.monthly_payment} onChange={(_, v) => update(idx, 'monthly_payment', v)} />
              <YesNoField label="Pay off at closing?" name={`payoff_${idx}`} cols={2}
                value={liab.pay_off_at_close} onChange={(_, v) => update(idx, 'pay_off_at_close', v)} />
            </div>
          </div>
        ))}
        <div className="urla-add-entry" style={{ gridColumn: '1 / -1' }}>
          <button type="button" className="urla-btn-link" onClick={add}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add another debt
          </button>
        </div>
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
