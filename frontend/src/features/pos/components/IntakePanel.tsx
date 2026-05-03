import React, { useState } from 'react';

export interface IntakeData {
  is_veteran: boolean | null;
  loan_purpose: 'purchase' | 'refinance' | null;
  has_co_borrower: boolean | null;
  co_borrowers: Array<{ first_name: string; last_name: string }>;
}

export const EMPTY_INTAKE: IntakeData = {
  is_veteran: null,
  loan_purpose: null,
  has_co_borrower: null,
  co_borrowers: [],
};

export interface IntakePanelProps {
  initial?: IntakeData;
  onComplete: (data: IntakeData) => void;
}

type IntakeStep = 'veteran' | 'purpose' | 'coborrower' | 'names';

function initialStep(data?: IntakeData): IntakeStep {
  if (!data) return 'veteran';
  if (data.is_veteran == null) return 'veteran';
  if (data.loan_purpose == null) return 'purpose';
  if (data.has_co_borrower == null) return 'coborrower';
  return 'veteran';
}

export const IntakePanel: React.FC<IntakePanelProps> = ({ initial, onComplete }) => {
  const [step, setStep] = useState<IntakeStep>(() => initialStep(initial));
  const [isVeteran, setIsVeteran] = useState<boolean | null>(initial?.is_veteran ?? null);
  const [loanPurpose, setLoanPurpose] = useState<'purchase' | 'refinance' | null>(initial?.loan_purpose ?? null);
  const [hasCoBorrower, setHasCoBorrower] = useState<boolean | null>(initial?.has_co_borrower ?? null);
  const [coBorrowers, setCoBorrowers] = useState<Array<{ first_name: string; last_name: string }>>(
    initial?.co_borrowers?.length ? initial.co_borrowers : [{ first_name: '', last_name: '' }],
  );

  const handleVeteranSelect = (val: boolean) => {
    setIsVeteran(val);
    setTimeout(() => setStep('purpose'), 300);
  };

  const handlePurposeSelect = (val: 'purchase' | 'refinance') => {
    setLoanPurpose(val);
    setTimeout(() => setStep('coborrower'), 300);
  };

  const handleCoBorrowerSelect = (val: boolean) => {
    setHasCoBorrower(val);
    if (val) {
      setTimeout(() => setStep('names'), 300);
    } else {
      onComplete({ is_veteran: isVeteran, loan_purpose: loanPurpose, has_co_borrower: false, co_borrowers: [] });
    }
  };

  const updateCoBorrower = (idx: number, field: 'first_name' | 'last_name', value: string) => {
    const updated = [...coBorrowers];
    updated[idx] = { ...updated[idx], [field]: value };
    setCoBorrowers(updated);
  };

  const addCoBorrower = () => {
    setCoBorrowers([...coBorrowers, { first_name: '', last_name: '' }]);
  };

  const removeCoBorrower = (idx: number) => {
    if (coBorrowers.length <= 1) return;
    setCoBorrowers(coBorrowers.filter((_, i) => i !== idx));
  };

  const handleNamesSubmit = () => {
    const valid = coBorrowers.filter(cb => cb.first_name.trim() && cb.last_name.trim());
    if (valid.length === 0) return;
    onComplete({ is_veteran: isVeteran, loan_purpose: loanPurpose, has_co_borrower: true, co_borrowers: valid });
  };

  const prevStep = (target: IntakeStep) => (
    <button type="button" className="pos-intake__back" onClick={() => setStep(target)}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="15 18 9 12 15 6" />
      </svg>
      Back
    </button>
  );

  return (
    <div className="pos-intake">
      <div className="pos-intake__header">
        <h1 className="pos-intake__title">Before we begin</h1>
        <p className="pos-intake__subtitle">
          A couple of quick questions to set up your application.
        </p>
      </div>

      {step === 'veteran' && (
        <div className="pos-intake__card" key="veteran">
          <h2 className="pos-intake__question">Are you a veteran or active-duty military?</h2>
          <p className="pos-intake__hint">This helps us determine if you may qualify for VA loan benefits.</p>
          <div className="pos-intake__choices">
            <button type="button" className={`pos-intake__choice${isVeteran === true ? ' is-selected' : ''}`}
              onClick={() => handleVeteranSelect(true)}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">Yes</span>
                <span className="pos-intake__choice-desc">Veteran, active duty, or reserve/guard</span>
              </span>
            </button>
            <button type="button" className={`pos-intake__choice${isVeteran === false ? ' is-selected' : ''}`}
              onClick={() => handleVeteranSelect(false)}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">No</span>
                <span className="pos-intake__choice-desc">Not affiliated with the military</span>
              </span>
            </button>
          </div>
        </div>
      )}

      {step === 'purpose' && (
        <div className="pos-intake__card" key="purpose">
          {prevStep('veteran')}
          <h2 className="pos-intake__question">What are you looking to do?</h2>
          <p className="pos-intake__hint">This determines the information we'll need from you.</p>
          <div className="pos-intake__choices">
            <button type="button" className={`pos-intake__choice${loanPurpose === 'purchase' ? ' is-selected' : ''}`}
              onClick={() => handlePurposeSelect('purchase')}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">Purchase</span>
                <span className="pos-intake__choice-desc">Buying a new home</span>
              </span>
            </button>
            <button type="button" className={`pos-intake__choice${loanPurpose === 'refinance' ? ' is-selected' : ''}`}
              onClick={() => handlePurposeSelect('refinance')}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">Refinance</span>
                <span className="pos-intake__choice-desc">Refinancing an existing mortgage</span>
              </span>
            </button>
          </div>
        </div>
      )}

      {step === 'coborrower' && (
        <div className="pos-intake__card" key="coborrower">
          {prevStep('purpose')}
          <h2 className="pos-intake__question">Will there be more than one borrower on this loan?</h2>
          <p className="pos-intake__hint">
            A co-borrower is someone applying for the loan with you — typically a spouse or partner.
            Each borrower completes their own application sections.
          </p>
          <div className="pos-intake__choices">
            <button type="button" className={`pos-intake__choice${hasCoBorrower === true ? ' is-selected' : ''}`}
              onClick={() => handleCoBorrowerSelect(true)}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">Yes</span>
                <span className="pos-intake__choice-desc">I have a co-borrower</span>
              </span>
            </button>
            <button type="button" className={`pos-intake__choice${hasCoBorrower === false ? ' is-selected' : ''}`}
              onClick={() => handleCoBorrowerSelect(false)}>
              <span className="pos-intake__choice-dot" />
              <span className="pos-intake__choice-text">
                <span className="pos-intake__choice-label">No</span>
                <span className="pos-intake__choice-desc">I'm applying alone</span>
              </span>
            </button>
          </div>
        </div>
      )}

      {step === 'names' && (
        <div className="pos-intake__card" key="names">
          {prevStep('coborrower')}
          <h2 className="pos-intake__question">Who is applying with you?</h2>
          <p className="pos-intake__hint">
            Each co-borrower will complete their own application after you finish yours.
          </p>

          <div className="pos-intake__names">
            {coBorrowers.map((cb, idx) => (
              <div key={idx} className="pos-intake__name-row">
                <span className="pos-intake__name-label">Co-borrower {coBorrowers.length > 1 ? idx + 1 : ''}</span>
                <div className="pos-intake__name-fields">
                  <input type="text" className="pos-intake__input" placeholder="First name"
                    value={cb.first_name} onChange={e => updateCoBorrower(idx, 'first_name', e.target.value)} />
                  <input type="text" className="pos-intake__input" placeholder="Last name"
                    value={cb.last_name} onChange={e => updateCoBorrower(idx, 'last_name', e.target.value)} />
                  {coBorrowers.length > 1 && (
                    <button type="button" className="pos-intake__remove" onClick={() => removeCoBorrower(idx)}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <button type="button" className="urla-btn-link" onClick={addCoBorrower} style={{ marginTop: 8 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add another co-borrower
          </button>

          <div className="pos-intake__submit">
            <button type="button" className="urla-btn urla-btn--primary" onClick={handleNamesSubmit}
              disabled={!coBorrowers.some(cb => cb.first_name.trim() && cb.last_name.trim())}>
              Continue to application
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
