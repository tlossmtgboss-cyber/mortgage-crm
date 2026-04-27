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

interface Account {
  type?: string;
  institution?: string;
  account_number_last4?: string;
  balance?: number | null;
}

export const AssetsPanel: React.FC<PanelProps> = ({ section, onChange, onComplete, onAskAria }) => {
  const { data, updateField } = usePanelData(section, onChange);
  const accounts: Account[] = (data.accounts as Account[]) || [{}];

  const updateAccount = (idx: number, key: keyof Account, value: unknown) => {
    const next = accounts.map((a, i) => (i === idx ? { ...a, [key]: value } : a));
    updateField('accounts', next);
  };

  const addAccount = () => updateField('accounts', [...accounts, {}]);

  const removeAccount = (idx: number) => {
    if (accounts.length === 1) return;
    updateField('accounts', accounts.filter((_, i) => i !== idx));
  };

  return (
    <>
      <FormSection
        title="Bank, retirement, and brokerage accounts"
        description="Add every account you'd like to use for the down payment, closing costs, or as reserves."
      >
        {accounts.map((acct, idx) => (
          <div key={idx} className="urla-subform" style={{ gridColumn: '1 / -1' }}>
            <div className="urla-subform__header">
              <span>Account {idx + 1}</span>
              {accounts.length > 1 && (
                <button type="button" className="urla-link-btn"
                  onClick={() => removeAccount(idx)}>Remove</button>
              )}
            </div>
            <div className="urla-form-grid">
              <SelectField label="Account type" name={`account_type_${idx}`} required cols={1}
                options={[
                  { value: 'checking', label: 'Checking' },
                  { value: 'savings', label: 'Savings' },
                  { value: 'money_market', label: 'Money market' },
                  { value: 'cd', label: 'Certificate of deposit' },
                  { value: 'retirement_401k', label: '401(k)' },
                  { value: 'retirement_ira', label: 'IRA' },
                  { value: 'brokerage', label: 'Brokerage' },
                  { value: 'gift', label: 'Gift funds' },
                ]}
                value={acct.type} onChange={(_, v) => updateAccount(idx, 'type', v)} />
              <TextField label="Institution" name={`institution_${idx}`} required cols={1}
                value={acct.institution} onChange={(_, v) => updateAccount(idx, 'institution', v)} />
              <TextField label="Last 4 of account number" name={`acctnum_${idx}`} cols={1}
                value={acct.account_number_last4}
                onChange={(_, v) => updateAccount(idx, 'account_number_last4', v)} />
              <TextField label="Current balance" name={`balance_${idx}`} type="currency" required cols={1}
                value={acct.balance} onChange={(_, v) => updateAccount(idx, 'balance', v)} />
            </div>
          </div>
        ))}
        <div style={{ gridColumn: '1 / -1' }}>
          <button type="button" className="urla-link-btn" onClick={addAccount}>
            + Add another account
          </button>
        </div>
      </FormSection>

      <FormSection title="Gift funds">
        <YesNoField label="Are you receiving any gift money for this loan?"
          name="receiving_gift" value={data.receiving_gift as boolean | null}
          onChange={updateField} cols={2} />
        {data.receiving_gift === true && (
          <>
            <TextField label="Gift amount" name="gift_amount" type="currency"
              value={data.gift_amount} onChange={updateField} cols={1} />
            <TextField label="Donor name" name="gift_donor"
              value={data.gift_donor} onChange={updateField} cols={1} />
            <SelectField label="Relationship to donor" name="gift_relationship"
              options={[
                { value: 'parent', label: 'Parent' },
                { value: 'spouse', label: 'Spouse / Partner' },
                { value: 'sibling', label: 'Sibling' },
                { value: 'grandparent', label: 'Grandparent' },
                { value: 'other_family', label: 'Other family' },
                { value: 'employer', label: 'Employer' },
                { value: 'other', label: 'Other' },
              ]}
              value={data.gift_relationship} onChange={updateField} cols={2} />
            {onAskAria && (
              <p style={{ gridColumn: '1 / -1' }} className="urla-helper-prompt">
                Not sure what's allowed?{' '}
                <button type="button" className="urla-link-btn" onClick={onAskAria}>
                  Ask Aria about gift fund eligibility
                </button>
              </p>
            )}
          </>
        )}
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
