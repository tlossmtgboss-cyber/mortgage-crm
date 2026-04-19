/**
 * Canonical document type display names.
 * Single source of truth — import this instead of defining local copies.
 */
export const DOC_TYPE_NAMES = {
  PAYSTUB: 'Pay Stubs',
  BANK_STATEMENT: 'Bank Statements',
  TAX_RETURN: 'Tax Returns',
  BUSINESS_TAX_RETURN: 'Business Tax Returns',
  W2: 'W-2 Forms',
  DRIVERS_LICENSE: "Driver's License",
  PURCHASE_CONTRACT: 'Purchase Contract',
  GIFT_LETTER: 'Gift Letter',
  PROFIT_LOSS: 'Profit & Loss Statement',
  BALANCE_SHEET: 'Balance Sheet',
  INVESTMENT_STATEMENT: 'Investment Statement',
  LOE: 'Letter of Explanation',
  LEASE_AGREEMENT: 'Lease Agreement',
  FHA_CERT: 'FHA Certificate',
  VA_COE: 'VA Certificate of Eligibility',
  DD214: 'DD-214',
  BANKRUPTCY_DISCHARGE: 'Bankruptcy Discharge',
  APPRAISAL: 'Appraisal',
  TITLE_REPORT: 'Title Report',
  HOMEOWNERS_INSURANCE: 'Homeowners Insurance',
  HOA: 'HOA Documents',
  OTHER: 'Other',
  // Legacy aliases
  PAYSTUBS: 'Pay Stubs',
  BANK_STATEMENTS: 'Bank Statements',
  TAX_RETURNS: 'Tax Returns',
  '1099': '1099 Forms',
  HOA_DOCS: 'HOA Documents',
};

export function getDocTypeName(docType) {
  if (!docType) return 'Document';
  const key = docType.toUpperCase();
  return DOC_TYPE_NAMES[key] || docType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
