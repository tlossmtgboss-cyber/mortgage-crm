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
  description?: string;
  creditor?: string;
  balance?: number | null;
  monthly_payment?: number | null;
}

export const LiabilitiesPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  const hasNonReporting = data.has_non_reporting_debts as boolean | null | undefined;
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
      <p className="urla-form-section__desc">
        Credit cards, auto loans, student loans, and other debts that appear on your credit
        report will be pulled automatically. You only need to list obligations that
        may <strong>not</strong> show up on credit.
      </p>

      <FormSection title="Do you have any debts not reported on credit?">
        <YesNoField
          label="Examples: child support, alimony, separate maintenance, garnishments, or payments on a co-signed loan"
          name="has_non_reporting_debts"
          value={hasNonReporting as boolean | null}
          onChange={updateField}
          cols={3}
        />
      </FormSection>

      {hasNonReporting === true && (
        <FormSection
          title="Non-reporting obligations"
          description="List each debt or obligation that does not appear on your credit report."
        >
          {liabilities.map((liab, idx) => (
            <div key={idx} className="urla-subform" style={{ gridColumn: '1 / -1' }}>
              <div className="urla-subform__header">
                <span>Obligation {idx + 1}</span>
                {liabilities.length > 1 && (
                  <button type="button" className="urla-btn-link urla-btn-link--danger"
                    onClick={() => remove(idx)}>Remove</button>
                )}
              </div>
              <div className="urla-form-grid">
                <SelectField label="Type" name={`liab_type_${idx}`} required cols={1}
                  options={[
                    { value: 'child_support', label: 'Child support' },
                    { value: 'alimony', label: 'Alimony' },
                    { value: 'separate_maintenance', label: 'Separate maintenance' },
                    { value: 'garnishment', label: 'Garnishment' },
                    { value: 'cosigned_loan', label: 'Co-signed loan' },
                    { value: 'private_loan', label: 'Private loan (no credit reporting)' },
                    { value: 'other', label: 'Other' },
                  ]}
                  value={liab.type} onChange={(_, v) => update(idx, 'type', v)} />
                <TextField label="Description" name={`desc_${idx}`} cols={1}
                  placeholder="e.g. Court order #, lender name"
                  value={liab.description} onChange={(_, v) => update(idx, 'description', v)} />
                <TextField label="Balance owed" name={`bal_${idx}`} type="currency" cols={1}
                  value={liab.balance} onChange={(_, v) => update(idx, 'balance', v)} />
                <TextField label="Monthly payment" name={`pmt_${idx}`} type="currency" required cols={1}
                  value={liab.monthly_payment} onChange={(_, v) => update(idx, 'monthly_payment', v)} />
              </div>
            </div>
          ))}
          <div className="urla-add-entry" style={{ gridColumn: '1 / -1' }}>
            <button type="button" className="urla-btn-link" onClick={add}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add another obligation
            </button>
          </div>
        </FormSection>
      )}

      {hasNonReporting === false && (
        <div className="urla-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <p>
            <strong>You're all set.</strong> Your credit-reporting debts will be pulled
            automatically when we run credit. No action needed here.
          </p>
        </div>
      )}

      <ContinueButton onClick={onComplete} />
    </>
  );
};
