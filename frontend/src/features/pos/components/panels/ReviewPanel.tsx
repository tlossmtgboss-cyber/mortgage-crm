import React, { useEffect, useState } from 'react';

import type { ApplicationSubmitResponse, SectionKey } from '../../types';
import { SECTION_LABELS, SECTION_ORDER } from '../../types';
import { validateSection } from '../../schemas/urla';
import { PanelProps } from './_shared';

const FIELD_LABELS: Record<string, string> = {
  first_name: 'First Name',
  last_name: 'Last Name',
  email: 'Email',
  phone: 'Phone',
  marital_status: 'Marital Status',
  dependents_count: 'Dependents',
  'current.street': 'Current Address',
  'current.city': 'City',
  'current.state': 'State',
  'current.zip': 'ZIP Code',
  'current.housing_status': 'Housing Status',
  'current.years_at_address': 'Years at Address',
  'current.monthly_cost': 'Monthly Housing Cost',
  employment_type: 'Employment Type',
  'employer.name': 'Employer Name',
  'employer.position': 'Position/Title',
  'employer.start_date': 'Start Date',
  'income.base': 'Base Income',
  'income.overtime': 'Overtime Income',
  'income.bonus': 'Bonus Income',
  'income.commission': 'Commission Income',
  accounts: 'Bank Accounts',
  receiving_gift: 'Gift Funds',
  liabilities: 'Liabilities',
  owns_other_property: 'Other Property Ownership',
  loan_purpose: 'Loan Purpose',
  loan_type: 'Loan Type',
  loan_amount: 'Loan Amount',
  'property.address': 'Property Address',
  'property.type': 'Property Type',
  'property.occupancy': 'Occupancy Type',
  'property.value': 'Property Value',
  will_occupy_as_primary: 'Primary Residence',
  has_recent_ownership: 'Recent Ownership',
  other_mortgage_on_property: 'Other Mortgage',
  borrowed_down_payment: 'Borrowed Down Payment',
  cosigner_on_other_loans: 'Co-Signer Status',
  outstanding_judgments: 'Outstanding Judgments',
  bankruptcy_7_years: 'Bankruptcy History',
  foreclosure_7_years: 'Foreclosure History',
  party_to_lawsuit: 'Lawsuit History',
  federal_debt_delinquent: 'Federal Debt',
  us_citizen: 'US Citizenship',
  permanent_resident: 'Permanent Resident',
};

function friendlyFieldName(path: string): string {
  return FIELD_LABELS[path] || path.replace(/[_.]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

interface SectionIssue {
  path: string;
  message: string;
  fieldName: string;
}

export const ReviewPanel: React.FC<PanelProps> = ({
  application,
  onSubmit,
  onAskAria,
  allSections,
  onNavigate,
}) => {
  const [acks, setAcks] = useState<{
    truth_certification: boolean;
    esign_consent: boolean;
    credit_authorization: boolean;
  }>({
    truth_certification: false,
    esign_consent: false,
    credit_authorization: false,
  });

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<ApplicationSubmitResponse | null>(null);

  if (!application) return null;

  const allAcked =
    acks.truth_certification && acks.esign_consent && acks.credit_authorization;

  const allSectionsComplete = SECTION_ORDER
    .filter(k => k !== 'review')
    .every(k => application.sections_complete[k] === true);

  const canSubmit = allSectionsComplete && allAcked && !submitting;

  const getIssuesForSection = (key: SectionKey): SectionIssue[] => {
    if (key === 'review' || key === 'schedule') return [];
    if (application.sections_complete[key]) return [];
    const sectionData = allSections?.[key]?.data;
    if (!sectionData) {
      return [{ path: '', message: 'Section not started', fieldName: 'Not started' }];
    }
    const result = validateSection(key, sectionData);
    if (result.ok) return [];
    return result.issues.map(issue => ({
      path: issue.path,
      message: issue.message,
      fieldName: friendlyFieldName(issue.path),
    }));
  };

  const handleSubmit = async () => {
    if (!onSubmit || !canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    const result = await onSubmit({
      appointment_id: application.submitted_appointment_id ?? null,
      acknowledged_certifications: Object.entries(acks)
        .filter(([, v]) => v)
        .map(([k]) => k),
    });
    setSubmitting(false);
    if (result) {
      setSubmitted(result);
    } else {
      setSubmitError(
        'We couldn\'t submit your application. Please check that every section is complete.',
      );
    }
  };

  if (submitted) {
    return (
      <div className="urla-confirm">
        <div className="urla-confirm__icon" aria-hidden>
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="9 12 11 14 16 9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h2>Application submitted</h2>
        <p className="urla-confirm__sub">
          Confirmation number: <strong>{submitted.confirmation_number}</strong>
        </p>

        <h3>What happens next</h3>
        <ol className="urla-confirm__steps">
          {submitted.next_steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      </div>
    );
  }

  return (
    <>
      <section className="urla-form-section">
        <h3 className="urla-form-section__title">Application summary</h3>
        <ul className="urla-recap">
          {SECTION_ORDER.filter(k => k !== 'review').map(key => {
            const isComplete = application.sections_complete[key] === true;
            const issues = getIssuesForSection(key);

            return (
              <li
                key={key}
                className={`urla-recap__item${isComplete ? ' is-complete' : ' is-incomplete'}`}
              >
                <div className="urla-recap__header">
                  <span className="urla-recap__icon">
                    {isComplete ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                    )}
                  </span>
                  {onNavigate ? (
                    <button
                      type="button"
                      className="urla-recap__section-link"
                      onClick={() => onNavigate(key)}
                    >
                      {SECTION_LABELS[key]}
                    </button>
                  ) : (
                    <span>{SECTION_LABELS[key]}</span>
                  )}
                  <span className={`urla-recap__status${isComplete ? '' : ' urla-recap__status--incomplete'}`}>
                    {isComplete ? 'Complete' : 'Incomplete'}
                  </span>
                </div>

                {!isComplete && issues.length > 0 && (
                  <ul className="urla-recap__issues">
                    {issues.map((issue, i) => (
                      <li key={i} className="urla-recap__issue">
                        {onNavigate && issue.path ? (
                          <button
                            type="button"
                            className="urla-recap__issue-link"
                            onClick={() => onNavigate(key, issue.path)}
                          >
                            <span className="urla-recap__issue-field">{issue.fieldName}</span>
                            <span className="urla-recap__issue-msg">— {issue.message}</span>
                          </button>
                        ) : (
                          <span>
                            <span className="urla-recap__issue-field">{issue.fieldName}</span>
                            <span className="urla-recap__issue-msg"> — {issue.message}</span>
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="urla-form-section">
        <h3 className="urla-form-section__title">Certifications & eSign</h3>
        <p className="urla-form-section__desc">
          Please review and confirm the following before submitting.
        </p>

        <CertCheckbox
          checked={acks.truth_certification}
          onChange={v => setAcks(a => ({ ...a, truth_certification: v }))}
          title="Truth certification"
          description={
            'I certify that the information provided is true and complete to the ' +
            'best of my knowledge. I understand that knowingly making false statements ' +
            'on this application is a federal offense.'
          }
        />

        <CertCheckbox
          checked={acks.esign_consent}
          onChange={v => setAcks(a => ({ ...a, esign_consent: v }))}
          title="Electronic signature consent"
          description={
            'I consent to use electronic records and signatures for this application ' +
            'and acknowledge that my electronic signature has the same legal effect as ' +
            'a handwritten one.'
          }
        />

        <CertCheckbox
          checked={acks.credit_authorization}
          onChange={v => setAcks(a => ({ ...a, credit_authorization: v }))}
          title="Credit authorization"
          description={
            'I authorize Perennia and its lending partners to obtain my credit report ' +
            'and verify the information on this application.'
          }
        />
      </section>

      <div className="urla-actions urla-actions--submit">
        {!allSectionsComplete && (
          <p className="urla-warn">
            Some sections are still incomplete — click a missing field above to go fix it.
          </p>
        )}
        {submitError && <p className="urla-warn">{submitError}</p>}
        {onAskAria && (
          <button type="button" className="urla-btn urla-btn--ghost" onClick={onAskAria}>
            Ask Aria something first
          </button>
        )}
        <button
          type="button"
          className="urla-btn urla-btn--primary urla-btn--large"
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          {submitting ? 'Submitting…' : 'Submit application'}
        </button>
      </div>
    </>
  );
};

const CertCheckbox: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  description: string;
}> = ({ checked, onChange, title, description }) => (
  <label className={`urla-cert${checked ? ' is-checked' : ''}`}>
    <input
      type="checkbox"
      checked={checked}
      onChange={e => onChange(e.target.checked)}
      className="urla-cert__input"
    />
    <span className="urla-cert__box" aria-hidden>
      {checked && (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </span>
    <span className="urla-cert__text">
      <span className="urla-cert__title">{title}</span>
      <span className="urla-cert__desc">{description}</span>
    </span>
  </label>
);
