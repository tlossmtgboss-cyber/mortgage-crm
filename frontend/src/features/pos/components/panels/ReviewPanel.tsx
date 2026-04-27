import React, { useState } from 'react';

import type { ApplicationSubmitResponse, BookingResponse } from '../../types';
import { SECTION_LABELS, SECTION_ORDER } from '../../types';
import { SmartCalendar } from '../SmartCalendar';
import { PanelProps } from './_shared';

/**
 * The Review & eSign step. Three things happen here:
 *   1. Recap of what's been completed
 *   2. Smart Calendar widget — borrower books their application review
 *   3. Three certification checkboxes + final Submit
 *
 * On successful submit, swaps to a confirmation view that displays the
 * confirmation_number and the next_steps list returned from the backend.
 */
export const ReviewPanel: React.FC<PanelProps> = ({ application, onSubmit, onAskAria }) => {
  const [booking, setBooking] = useState<BookingResponse | null>(null);

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

  const handleSubmit = async () => {
    if (!onSubmit || !canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    const result = await onSubmit({
      appointment_id: booking?.appointment_id ?? null,
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

  // ---------- confirmation view ----------

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

  // ---------- main view ----------

  return (
    <>
      {/* Section-by-section recap */}
      <section className="urla-form-section">
        <h3 className="urla-form-section__title">Application summary</h3>
        <ul className="urla-recap">
          {SECTION_ORDER.filter(k => k !== 'review').map(key => (
            <li
              key={key}
              className={`urla-recap__item${
                application.sections_complete[key] ? ' is-complete' : ' is-incomplete'
              }`}
            >
              <span>{SECTION_LABELS[key]}</span>
              <span>{application.sections_complete[key] ? 'Complete' : 'Incomplete'}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Smart Calendar */}
      <section className="urla-form-section">
        <h3 className="urla-form-section__title">Schedule your application review</h3>
        <p className="urla-form-section__desc">
          Pick a time to walk through your application together. Your loan officer
          will go through everything and answer any final questions before submission.
        </p>
        <SmartCalendar
          applicationId={application.id}
          onBooked={setBooking}
        />
      </section>

      {/* Certifications */}
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

      {/* Submit */}
      <div className="urla-actions urla-actions--submit">
        {!allSectionsComplete && (
          <p className="urla-warn">
            Some sections are still incomplete — go back and finish them before submitting.
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
