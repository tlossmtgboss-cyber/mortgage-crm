/**
 * SLA Dates / Important Dates tab -- tracks all milestone dates
 * through the loan lifecycle (Salesforce "Custom Byte Mapping" SLA dates).
 */
import React from 'react';

interface SLADatesTabProps {
  formData: Record<string, any>;
  onFieldChange: (field: string, value: any) => void;
}

interface DateFieldProps {
  label: string;
  field: string;
  hint?: string;
  formData: Record<string, any>;
  onFieldChange: (field: string, value: any) => void;
}

function DateField({ label, field, hint, formData, onFieldChange }: DateFieldProps) {
  return (
    <div className="date-field">
      <label>{label}</label>
      <input
        type="date"
        value={formData[field] || ''}
        onChange={(e) => onFieldChange(field, e.target.value)}
      />
      {hint && <small className="field-hint">{hint}</small>}
    </div>
  );
}

interface DateSectionProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

function DateSection({ title, subtitle, children }: DateSectionProps) {
  return (
    <div className="dates-section">
      <h3 className="dates-section-title">{title}</h3>
      <p className="section-subtitle">{subtitle}</p>
      <div className="dates-grid">{children}</div>
    </div>
  );
}

export default function SLADatesTab({ formData, onFieldChange }: SLADatesTabProps) {
  const dfProps = { formData, onFieldChange };

  return (
    <div className="tab-content sla-dates-tab">
      {/* Lead & Application Phase */}
      <DateSection title="Lead & Application Phase" subtitle="Initial contact through application submission">
        <DateField label="Prospect Date" field="prospect_date" {...dfProps} />
        <DateField label="Application Date" field="application_date" {...dfProps} />
        <DateField label="LE Pending Date" field="le_pending_date" hint="Loan Estimate disclosure" {...dfProps} />
        <DateField label="Credit Only Date" field="credit_only_date" {...dfProps} />
        <DateField label="File Received Date" field="file_received_date" {...dfProps} />
        <DateField label="Pre-Approval Date" field="preapproval_date" {...dfProps} />
      </DateSection>

      {/* Lock Phase */}
      <DateSection title="Lock Phase" subtitle="Rate lock management">
        <DateField label="Lock Date" field="lock_date" {...dfProps} />
        <DateField label="Lock Expiration Date" field="lock_expiration_date" {...dfProps} />
      </DateSection>

      {/* Processing & Underwriting Phase */}
      <DateSection title="Processing & Underwriting" subtitle="File processing through underwriting decision">
        <DateField label="UW Received Date" field="uw_received_date" hint="File received by underwriting" {...dfProps} />
        <DateField label="Conditions for Review Date" field="conditions_for_review_date" {...dfProps} />
        <DateField label="Suspended Date" field="suspended_date" {...dfProps} />
        <DateField label="Loan Approved Date" field="loan_approved_date" {...dfProps} />
        <DateField label="Approved Not Accepted Date" field="approved_not_accepted_date" {...dfProps} />
        <DateField label="Approval Expires Date" field="approval_expires_date" {...dfProps} />
      </DateSection>

      {/* Appraisal Phase */}
      <DateSection title="Appraisal" subtitle="Property appraisal process">
        <DateField label="Appraisal Ordered Date" field="appraisal_ordered_date" {...dfProps} />
        <DateField label="Appraisal Received Date" field="appraisal_received_date" {...dfProps} />
        <DateField label="Appraisal Scheduled Date" field="appraisal_scheduled_date" {...dfProps} />
        <DateField label="Appraisal Completed Date" field="appraisal_completed_date" {...dfProps} />
        <DateField label="Appraisal Docs Expire Date" field="appraisal_docs_expire_date" {...dfProps} />
      </DateSection>

      {/* Title & Insurance Phase */}
      <DateSection title="Title & Insurance" subtitle="Title and insurance order tracking">
        <DateField label="Title Ordered Date" field="title_ordered_date" {...dfProps} />
        <DateField label="Title Received Date" field="title_received_date" {...dfProps} />
        <DateField label="Insurance Ordered Date" field="insurance_ordered_date" {...dfProps} />
        <DateField label="Insurance Received Date" field="insurance_received_date" {...dfProps} />
      </DateSection>

      {/* Closing Disclosure Phase */}
      <DateSection title="Closing Disclosure" subtitle="CD preparation and acknowledgment">
        <DateField label="CD Requested Date" field="cd_requested_date" {...dfProps} />
        <DateField label="CD Sent to Borrower Date" field="cd_sent_to_borrower_date" {...dfProps} />
        <DateField label="CD Acknowledged Date" field="cd_acknowledged_date" {...dfProps} />
      </DateSection>

      {/* Clear to Close & Docs Phase */}
      <DateSection title="Clear to Close & Docs" subtitle="Final approval and document preparation">
        <DateField label="Clear to Close Date" field="clear_to_close_date" {...dfProps} />
        <DateField label="Docs Ordered Date" field="docs_ordered_date" {...dfProps} />
        <DateField label="Docs Out Date" field="docs_out_date" {...dfProps} />
        <DateField label="Credit Docs Expire Date" field="credit_docs_expire_date" {...dfProps} />
      </DateSection>

      {/* Funding & Closing Phase */}
      <DateSection title="Funding & Closing" subtitle="Final funding and closing dates">
        <DateField label="Scheduled Closing Date" field="scheduled_closing_date" {...dfProps} />
        <DateField label="Scheduled Funding Date" field="scheduled_funding_date" {...dfProps} />
        <DateField label="Funds Ordered Date" field="funds_ordered_date" {...dfProps} />
        <DateField label="Funds Sent Date" field="funds_sent_date" {...dfProps} />
        <DateField label="Funded Date" field="funded_date" {...dfProps} />
        <DateField label="Closing Date" field="closing_date" {...dfProps} />
        <DateField label="First Payment Date" field="first_payment_date" {...dfProps} />
      </DateSection>

      {/* Post-Closing & Status */}
      <DateSection title="Post-Closing & Status" subtitle="Post-funding and status change dates">
        <DateField label="Investor Purchased Date" field="investor_purchased_date" {...dfProps} />
        <DateField label="Withdrawn Date" field="withdrawn_date" {...dfProps} />
        <DateField label="Contract Received Date" field="contract_received_date" {...dfProps} />
      </DateSection>
    </div>
  );
}
