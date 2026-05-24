/**
 * ReconciliationCenter - Constants
 *
 * Stage options and field type definitions used across the reconciliation UI.
 */

// All stages for dropdown - Lead stages, Active Loan stages, and MUM/Portfolio stages
export const ALL_STAGES = [
  // Lead Stages
  { value: 'NEW', label: 'New Lead', category: 'Lead' },
  { value: 'ATTEMPTED_CONTACT', label: 'Attempted Contact', category: 'Lead' },
  { value: 'PROSPECT', label: 'Prospect', category: 'Lead' },
  { value: 'APPLICATION', label: 'Application', category: 'Lead' },
  { value: 'APPLICATION_STARTED', label: 'Application Started', category: 'Lead' },
  { value: 'PRE_QUALIFIED', label: 'Pre-Qualified', category: 'Lead' },
  { value: 'PRE_APPROVED', label: 'Pre-Approved', category: 'Lead' },
  { value: 'UNDER_CONTRACT', label: 'Under Contract', category: 'Lead' },
  { value: 'LONG_TERM_NURTURE', label: 'Long-Term Nurture', category: 'Lead' },
  // Active Loan Stages
  { value: 'DISCLOSED', label: 'Disclosed', category: 'Active Loan' },
  { value: 'PROCESSING', label: 'Processing', category: 'Active Loan' },
  { value: 'UW_RECEIVED', label: 'Underwriting Received', category: 'Active Loan' },
  { value: 'APPROVED', label: 'Approved', category: 'Active Loan' },
  { value: 'CTC', label: 'Clear to Close', category: 'Active Loan' },
  { value: 'SUSPENDED', label: 'Suspended', category: 'Active Loan' },
  { value: 'FUNDED', label: 'Funded', category: 'Active Loan' },
  // MUM / Portfolio Stages
  { value: 'CLOSED', label: 'Closed (Portfolio)', category: 'MUM' },
  { value: 'AMR', label: 'Annual Mortgage Review', category: 'MUM' },
  { value: 'REFERRAL_SOURCE', label: 'Referral Source', category: 'MUM' },
  // Other
  { value: 'WITHDRAWN', label: 'Withdrawn', category: 'Other' },
  { value: 'DOES_NOT_QUALIFY', label: 'Does Not Qualify', category: 'Other' }
];

// Available field types for renaming dropdown
export const FIELD_TYPE_OPTIONS = [
  { value: 'first_name', label: 'First Name' },
  { value: 'last_name', label: 'Last Name' },
  { value: 'borrower_name', label: 'Borrower Name' },
  { value: 'coborrower_first_name', label: 'Co-Borrower First Name' },
  { value: 'coborrower_last_name', label: 'Co-Borrower Last Name' },
  { value: 'coborrower_name', label: 'Co-Borrower Name' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'loan_number', label: 'Loan Number' },
  { value: 'property_address', label: 'Property Address' },
  { value: 'property_city', label: 'Property City' },
  { value: 'property_state', label: 'Property State' },
  { value: 'property_zip', label: 'Property Zip' },
  { value: 'loan_amount', label: 'Loan Amount' },
  { value: 'amount', label: 'Amount' },
  { value: 'lender', label: 'Lender' },
  { value: 'processor', label: 'Processor' },
  { value: 'processing_assistant', label: 'Processing Assistant' },
  { value: 'loan_officer', label: 'Loan Officer' },
  { value: 'loan_officer_name', label: 'Loan Officer Name' },
  { value: 'program', label: 'Program' },
  { value: 'interest_rate', label: 'Interest Rate' },
  { value: 'closing_date', label: 'Closing Date' },
  { value: 'lock_expiration', label: 'Lock Expiration' },
  { value: 'referral_partner', label: 'Referral Partner' },
  { value: 'realtor_name', label: 'Realtor Name' },
  { value: 'notes', label: 'Notes' }
];
