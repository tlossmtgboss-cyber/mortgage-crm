/**
 * ExtractionsSection Component
 *
 * Displays extracted data from call intelligence processing.
 * Shows identity, property, employment, financial, and intent data
 * extracted from call transcripts.
 */

import React, { useState } from 'react';
import './ExtractionsSection.css';

// Confidence level badge
const ConfidenceBadge = ({ score }) => {
  if (score === undefined || score === null) return null;

  let level = 'low';
  if (score >= 90) level = 'high';
  else if (score >= 70) level = 'medium';

  return (
    <span className={`confidence-badge ${level}`}>
      {Math.round(score)}%
    </span>
  );
};

// Single extraction field display
const ExtractionField = ({ label, value, confidence, sourceText }) => {
  const [showSource, setShowSource] = useState(false);

  if (value === undefined || value === null || value === '') return null;

  // Format value based on type
  const formatValue = (val) => {
    if (typeof val === 'boolean') return val ? 'Yes' : 'No';
    if (typeof val === 'number') {
      // Check if it looks like a currency value
      if (label.toLowerCase().includes('amount') ||
          label.toLowerCase().includes('price') ||
          label.toLowerCase().includes('income') ||
          label.toLowerCase().includes('salary')) {
        return new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          maximumFractionDigits: 0
        }).format(val);
      }
      return val.toLocaleString();
    }
    if (Array.isArray(val)) return val.join(', ');
    return String(val);
  };

  return (
    <div className="extraction-field">
      <div className="field-header">
        <span className="field-label">{label}</span>
        <ConfidenceBadge score={confidence} />
      </div>
      <div className="field-value">{formatValue(value)}</div>
      {sourceText && (
        <button
          className="source-toggle"
          onClick={() => setShowSource(!showSource)}
        >
          {showSource ? 'Hide source' : 'Show source'}
        </button>
      )}
      {showSource && sourceText && (
        <div className="source-text">
          <em>"{sourceText}"</em>
        </div>
      )}
    </div>
  );
};

// Extraction category card
const ExtractionCard = ({ title, icon, fields, isEmpty }) => {
  const [expanded, setExpanded] = useState(true);

  if (isEmpty) return null;

  return (
    <div className={`extraction-card ${expanded ? 'expanded' : 'collapsed'}`}>
      <div
        className="card-header"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="card-title">
          <span className="card-icon">{icon}</span>
          <h4>{title}</h4>
        </div>
        <span className="expand-icon">{expanded ? '−' : '+'}</span>
      </div>
      {expanded && (
        <div className="card-content">
          {fields}
        </div>
      )}
    </div>
  );
};

const ExtractionsSection = ({
  extractions = {},
  callOutcome = null,
  sessionId,
  onApproveExtraction,
  onRejectExtraction
}) => {
  // Parse extractions from artifacts if needed
  const identity = extractions.identity || {};
  const property = extractions.property || {};
  const employment = extractions.employment || {};
  const financial = extractions.financial || {};
  const compliance = extractions.compliance || {};
  const intent = extractions.intent || {};

  const hasIdentity = Object.keys(identity).length > 0;
  const hasProperty = Object.keys(property).length > 0;
  const hasEmployment = Object.keys(employment).length > 0;
  const hasFinancial = Object.keys(financial).length > 0;
  const hasCompliance = Object.keys(compliance).length > 0;
  const hasIntent = Object.keys(intent).length > 0;
  const hasCallOutcome = callOutcome && Object.keys(callOutcome).length > 0;

  const hasAnyData = hasIdentity || hasProperty || hasEmployment ||
                     hasFinancial || hasCompliance || hasIntent || hasCallOutcome;

  if (!hasAnyData) {
    return (
      <div className="extractions-section empty">
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <h3>No Extracted Data</h3>
          <p>Data extraction results will appear here once the call is processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="extractions-section">
      <div className="section-header">
        <h3>Extracted Information</h3>
        <p className="section-subtitle">
          AI-extracted data from call transcript. Review for accuracy before applying to loan file.
        </p>
      </div>

      <div className="extractions-grid">
        {/* Call Outcome */}
        {hasCallOutcome && (
          <ExtractionCard
            title="Call Outcome"
            icon="📞"
            fields={
              <>
                <ExtractionField
                  label="Outcome"
                  value={callOutcome.outcome}
                  confidence={callOutcome.confidence}
                />
                <ExtractionField
                  label="Next Action"
                  value={callOutcome.next_action}
                />
                <ExtractionField
                  label="Borrower Sentiment"
                  value={callOutcome.borrower_sentiment}
                />
                <ExtractionField
                  label="Callback Scheduled"
                  value={callOutcome.callback_scheduled}
                />
                <ExtractionField
                  label="Callback Date"
                  value={callOutcome.callback_date}
                />
                <ExtractionField
                  label="Application Started"
                  value={callOutcome.application_started}
                />
                <ExtractionField
                  label="Follow-up Required"
                  value={callOutcome.follow_up_required}
                />
              </>
            }
          />
        )}

        {/* Identity */}
        {hasIdentity && (
          <ExtractionCard
            title="Identity"
            icon="👤"
            fields={
              <>
                <ExtractionField
                  label="Full Name"
                  value={identity.full_name}
                  confidence={identity.full_name_confidence}
                  sourceText={identity.full_name_source}
                />
                <ExtractionField
                  label="First Name"
                  value={identity.first_name}
                  confidence={identity.first_name_confidence}
                />
                <ExtractionField
                  label="Last Name"
                  value={identity.last_name}
                  confidence={identity.last_name_confidence}
                />
                <ExtractionField
                  label="Email"
                  value={identity.email}
                  confidence={identity.email_confidence}
                />
                <ExtractionField
                  label="Phone"
                  value={identity.phone}
                  confidence={identity.phone_confidence}
                />
                <ExtractionField
                  label="SSN Last 4"
                  value={identity.ssn_last_four ? `****${identity.ssn_last_four}` : null}
                  confidence={identity.ssn_last_four_confidence}
                />
                <ExtractionField
                  label="Date of Birth"
                  value={identity.date_of_birth}
                  confidence={identity.date_of_birth_confidence}
                />
                <ExtractionField
                  label="Marital Status"
                  value={identity.marital_status}
                  confidence={identity.marital_status_confidence}
                />
                <ExtractionField
                  label="Current Address"
                  value={identity.current_address}
                  confidence={identity.current_address_confidence}
                />
              </>
            }
          />
        )}

        {/* Property */}
        {hasProperty && (
          <ExtractionCard
            title="Property"
            icon="🏠"
            fields={
              <>
                <ExtractionField
                  label="Property Address"
                  value={property.address}
                  confidence={property.address_confidence}
                  sourceText={property.address_source}
                />
                <ExtractionField
                  label="Property Type"
                  value={property.property_type}
                  confidence={property.property_type_confidence}
                />
                <ExtractionField
                  label="Purchase Price"
                  value={property.purchase_price}
                  confidence={property.purchase_price_confidence}
                />
                <ExtractionField
                  label="Estimated Value"
                  value={property.estimated_value}
                  confidence={property.estimated_value_confidence}
                />
                <ExtractionField
                  label="Occupancy"
                  value={property.occupancy_type}
                  confidence={property.occupancy_type_confidence}
                />
                <ExtractionField
                  label="Number of Units"
                  value={property.number_of_units}
                />
                <ExtractionField
                  label="Year Built"
                  value={property.year_built}
                />
                <ExtractionField
                  label="HOA"
                  value={property.has_hoa}
                />
                <ExtractionField
                  label="HOA Amount"
                  value={property.hoa_amount}
                />
              </>
            }
          />
        )}

        {/* Employment */}
        {hasEmployment && (
          <ExtractionCard
            title="Employment"
            icon="💼"
            fields={
              <>
                <ExtractionField
                  label="Employer Name"
                  value={employment.employer_name}
                  confidence={employment.employer_name_confidence}
                  sourceText={employment.employer_name_source}
                />
                <ExtractionField
                  label="Job Title"
                  value={employment.job_title}
                  confidence={employment.job_title_confidence}
                />
                <ExtractionField
                  label="Employment Type"
                  value={employment.employment_type}
                  confidence={employment.employment_type_confidence}
                />
                <ExtractionField
                  label="Years at Job"
                  value={employment.years_at_job}
                  confidence={employment.years_at_job_confidence}
                />
                <ExtractionField
                  label="Monthly Income"
                  value={employment.monthly_income}
                  confidence={employment.monthly_income_confidence}
                />
                <ExtractionField
                  label="Annual Income"
                  value={employment.annual_income}
                  confidence={employment.annual_income_confidence}
                />
                <ExtractionField
                  label="Self Employed"
                  value={employment.is_self_employed}
                />
                <ExtractionField
                  label="Business Name"
                  value={employment.business_name}
                />
              </>
            }
          />
        )}

        {/* Financial */}
        {hasFinancial && (
          <ExtractionCard
            title="Financial"
            icon="💰"
            fields={
              <>
                <ExtractionField
                  label="Total Monthly Income"
                  value={financial.total_monthly_income}
                  confidence={financial.total_monthly_income_confidence}
                />
                <ExtractionField
                  label="Total Assets"
                  value={financial.total_assets}
                  confidence={financial.total_assets_confidence}
                />
                <ExtractionField
                  label="Checking/Savings"
                  value={financial.checking_savings}
                />
                <ExtractionField
                  label="Retirement Accounts"
                  value={financial.retirement_accounts}
                />
                <ExtractionField
                  label="Down Payment"
                  value={financial.down_payment_amount}
                  confidence={financial.down_payment_amount_confidence}
                />
                <ExtractionField
                  label="Down Payment Source"
                  value={financial.down_payment_source}
                />
                <ExtractionField
                  label="Monthly Debts"
                  value={financial.monthly_debt_payments}
                />
                <ExtractionField
                  label="Credit Score (Stated)"
                  value={financial.stated_credit_score}
                  confidence={financial.stated_credit_score_confidence}
                />
              </>
            }
          />
        )}

        {/* Intent / Loan Purpose */}
        {hasIntent && (
          <ExtractionCard
            title="Loan Intent"
            icon="🎯"
            fields={
              <>
                <ExtractionField
                  label="Loan Purpose"
                  value={intent.loan_purpose}
                  confidence={intent.loan_purpose_confidence}
                  sourceText={intent.loan_purpose_source}
                />
                <ExtractionField
                  label="Loan Type Preference"
                  value={intent.loan_type_preference}
                />
                <ExtractionField
                  label="Loan Amount"
                  value={intent.loan_amount}
                  confidence={intent.loan_amount_confidence}
                />
                <ExtractionField
                  label="Timeline"
                  value={intent.timeline}
                  confidence={intent.timeline_confidence}
                />
                <ExtractionField
                  label="Urgency Level"
                  value={intent.urgency_level}
                />
                <ExtractionField
                  label="Has Real Estate Agent"
                  value={intent.has_realtor}
                />
                <ExtractionField
                  label="Agent Name"
                  value={intent.realtor_name}
                />
                <ExtractionField
                  label="Pre-Approved Elsewhere"
                  value={intent.pre_approved_elsewhere}
                />
                <ExtractionField
                  label="First Time Homebuyer"
                  value={intent.first_time_homebuyer}
                />
              </>
            }
          />
        )}

        {/* Compliance */}
        {hasCompliance && (
          <ExtractionCard
            title="Compliance Notes"
            icon="📋"
            fields={
              <>
                <ExtractionField
                  label="Citizenship Status"
                  value={compliance.citizenship_status}
                  confidence={compliance.citizenship_status_confidence}
                />
                <ExtractionField
                  label="Has Bankruptcy"
                  value={compliance.has_bankruptcy}
                />
                <ExtractionField
                  label="Bankruptcy Details"
                  value={compliance.bankruptcy_details}
                />
                <ExtractionField
                  label="Has Foreclosure"
                  value={compliance.has_foreclosure}
                />
                <ExtractionField
                  label="Outstanding Judgments"
                  value={compliance.outstanding_judgments}
                />
                <ExtractionField
                  label="Alimony/Child Support"
                  value={compliance.alimony_child_support}
                />
                <ExtractionField
                  label="Co-Borrower Mentioned"
                  value={compliance.co_borrower_mentioned}
                />
              </>
            }
          />
        )}
      </div>
    </div>
  );
};

export default ExtractionsSection;
