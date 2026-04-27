import React from 'react';

import {
  ContinueButton,
  FormSection,
  PanelProps,
  YesNoField,
  usePanelData,
} from './_shared';

/**
 * URLA Section 5 declarations. These map directly to FNMA Form 1003
 * checkboxes — every "yes" potentially triggers an underwriting condition
 * or document request, so the Aria escalation rate tends to be highest on
 * this step.
 */
export const DeclarationsPanel: React.FC<PanelProps> = ({ section, onChange, onComplete }) => {
  const { data, updateField } = usePanelData(section, onChange);

  return (
    <>
      <FormSection
        title="About the property and your finances"
        description="A few standard questions required by the URLA. Answer accurately — discrepancies discovered later can delay or jeopardize your loan."
      >
        <YesNoField label="Will you occupy the property as your primary residence?"
          name="will_occupy_as_primary"
          value={data.will_occupy_as_primary as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Have you had an ownership interest in another property in the last 3 years?"
          name="has_recent_ownership"
          value={data.has_recent_ownership as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you taking out any other loan or mortgage on this property?"
          name="other_mortgage_on_property"
          value={data.other_mortgage_on_property as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Will any portion of the down payment be borrowed?"
          name="borrowed_down_payment"
          value={data.borrowed_down_payment as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you a co-signer or guarantor on any other loans?"
          name="cosigner_on_other_loans"
          value={data.cosigner_on_other_loans as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are there any outstanding judgments against you?"
          name="outstanding_judgments"
          value={data.outstanding_judgments as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Have you been declared bankrupt within the past 7 years?"
          name="bankruptcy_7_years"
          value={data.bankruptcy_7_years as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Have you had property foreclosed on in the last 7 years?"
          name="foreclosure_7_years"
          value={data.foreclosure_7_years as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you a party to a lawsuit?"
          name="party_to_lawsuit"
          value={data.party_to_lawsuit as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you currently delinquent on any federal debt (e.g., student loans, taxes)?"
          name="federal_debt_delinquent"
          value={data.federal_debt_delinquent as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you a U.S. citizen?"
          name="us_citizen" value={data.us_citizen as boolean | null}
          onChange={updateField} cols={3} />

        <YesNoField label="Are you a permanent resident alien?"
          name="permanent_resident" value={data.permanent_resident as boolean | null}
          onChange={updateField} cols={3} />
      </FormSection>

      <ContinueButton onClick={onComplete} />
    </>
  );
};
