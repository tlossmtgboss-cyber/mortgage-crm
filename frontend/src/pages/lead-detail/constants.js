/**
 * Constants for LeadDetail page — status options, circle contact types, status colors.
 */

// Status options — all stages across Lead, Active Loan, and MUM
export const statusOptions = [
  // Lead stages
  { label: 'Lead Stages', isHeader: true },
  'New',
  'Attempted Contact',
  'Prospect',
  'Application',
  'Pre-Qualified',
  'Pre-Approved',
  'Long-Term Nurture',
  'Credit Repair',
  'Withdrawn',
  'Does Not Qualify',
  'Do Not Call',
  // Active Loan stages
  { label: 'Active Loan Stages', isHeader: true },
  'Disclosed',
  'Processing',
  'Submitted',
  'Underwriting',
  'UW Received',
  'Conditional Approval',
  'Approved',
  'Suspended',
  'CTC',
  'Clear to Close',
  'Closing',
  'Docs',
  'Docs Out',
  'Cancelled',
  'Denied',
  'Dead',
  // MUM (Funded)
  { label: 'MUM / Closed', isHeader: true },
  'Funded',
];

export const circleContactTypes = [
  { value: 'Co-Borrower', icon: '\u{1F465}' },
  { value: 'Real Estate Agent', icon: '\u{1F3E1}' },
  { value: 'Family Member', icon: '\u{1F468}‍\u{1F469}‍\u{1F467}' },
  { value: 'Attorney', icon: '⚖️' },
  { value: 'Financial Advisor', icon: '\u{1F4BC}' },
  { value: 'Insurance Agent', icon: '\u{1F6E1}️' },
  { value: 'Life Insurance Agent', icon: '\u{1F6E1}️' },
  { value: 'Accountant', icon: '\u{1F4CA}' },
  { value: 'Estate Planner', icon: '\u{1F4DC}' },
  { value: 'Other Contact', icon: '\u{1F91D}' }
];

// Get color for status badge
export const getStatusColor = (status) => {
  const colors = {
    // Lead stages
    'New': '#2196F3',
    'Attempted Contact': '#FF9800',
    'Prospect': '#9C27B0',
    'Application': '#00BCD4',
    'Pre-Qualified': '#4CAF50',
    'Pre-Approved': '#8BC34A',
    'Long-Term Nurture': '#607D8B',
    'Withdrawn': '#F44336',
    'Does Not Qualify': '#795548',
    // Active Loan stages
    'Disclosed': '#00C853',
    'Processing': '#FF9800',
    'Submitted': '#FF9800',
    'Underwriting': '#FFC107',
    'UW Received': '#FFC107',
    'Conditional Approval': '#00BCD4',
    'Approved': '#4CAF50',
    'Suspended': '#F44336',
    'CTC': '#4CAF50',
    'Clear to Close': '#4CAF50',
    'Closing': '#4CAF50',
    'Docs': '#4CAF50',
    'Docs Out': '#4CAF50',
    'Cancelled': '#F44336',
    'Denied': '#F44336',
    'Dead': '#9E9E9E',
    // MUM
    'Funded': '#FFD700',
  };
  return colors[status] || '#999';
};

export const getContactIcon = (type) => {
  const found = circleContactTypes.find(t => t.value === type);
  return found ? found.icon : '\u{1F91D}';
};
