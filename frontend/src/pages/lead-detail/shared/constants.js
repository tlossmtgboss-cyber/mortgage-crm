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

export const circleContactTypes = [
  { value: 'Co-Borrower', icon: '\u{1F465}' },
  { value: 'Real Estate Agent', icon: '\u{1F3E1}' },
  { value: 'Family Member', icon: '\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}' },
  { value: 'Attorney', icon: '\u{2696}\u{FE0F}' },
  { value: 'Financial Advisor', icon: '\u{1F4BC}' },
  { value: 'Insurance Agent', icon: '\u{1F6E1}\u{FE0F}' },
  { value: 'Life Insurance Agent', icon: '\u{1F6E1}\u{FE0F}' },
  { value: 'Accountant', icon: '\u{1F4CA}' },
  { value: 'Estate Planner', icon: '\u{1F4DC}' },
  { value: 'Other Contact', icon: '\u{1F91D}' }
];

// Mock lead data generator (same as Leads.js)
export const generateMockLeads = () => {
  const currentDate = new Date();

  return [
    { id: 1, name: 'Sarah Johnson', email: 'sarah.johnson@email.com', phone: '(555) 123-4567', stage: 'New', source: 'Website', credit_score: 720, loan_amount: 425000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 85, next_action: 'Initial Contact' },
    { id: 2, name: 'Michael Chen', email: 'mchen@email.com', phone: '(555) 234-5678', stage: 'New', source: 'Referral - Amy Smith', credit_score: 695, loan_amount: 380000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 1 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 78, next_action: 'Call to Schedule Meeting' },
    { id: 3, name: 'Emily Rodriguez', email: 'emily.r@email.com', phone: '(555) 345-6789', stage: 'New', source: 'Social Media', credit_score: 0, loan_amount: 295000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 3 * 60 * 60 * 1000).toISOString(), ai_score: 72, next_action: 'Send Pre-Qual Email' },
    { id: 4, name: 'David Martinez', email: 'david.m@email.com', phone: '(555) 456-7890', stage: 'Attempted Contact', source: 'Zillow', credit_score: 710, loan_amount: 550000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 4 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 80, next_action: 'Follow-up Call', contact_attempts: 2 },
    { id: 5, name: 'Jennifer Lee', email: 'jlee@email.com', phone: '(555) 567-8901', stage: 'Attempted Contact', source: 'Facebook', credit_score: 685, loan_amount: 340000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 5 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 65, next_action: 'Send SMS', contact_attempts: 1 },
    { id: 6, name: 'Robert Taylor', email: 'rtaylor@email.com', phone: '(555) 678-9012', stage: 'Prospect', source: 'Referral - Bob Johnson', credit_score: 745, loan_amount: 620000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 92, next_action: 'Schedule Pre-Approval Meeting' },
    { id: 7, name: 'Amanda Wilson', email: 'awilson@email.com', phone: '(555) 789-0123', stage: 'Prospect', source: 'Website', credit_score: 702, loan_amount: 415000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 8 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 88, next_action: 'Send Rate Quote' },
    { id: 8, name: 'James Anderson', email: 'j.anderson@email.com', phone: '(555) 890-1234', stage: 'Prospect', source: 'Realtor.com', credit_score: 678, loan_amount: 365000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 9 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 74, next_action: 'Discuss Programs' },
    { id: 9, name: 'Lisa Brown', email: 'lbrown@email.com', phone: '(555) 901-2345', stage: 'Pre-Qualified', source: 'Referral - Amy Smith', credit_score: 725, loan_amount: 485000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 12 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 90, next_action: 'Start Application' },
    { id: 10, name: 'Christopher Davis', email: 'cdavis@email.com', phone: '(555) 012-3456', stage: 'Pre-Qualified', source: 'Website', credit_score: 698, loan_amount: 395000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 14 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 82, next_action: 'Find Realtor' },
    { id: 11, name: 'Michelle Garcia', email: 'mgarcia@email.com', phone: '(555) 123-7890', stage: 'Application', source: 'Zillow', credit_score: 715, loan_amount: 535000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 16 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 87, next_action: 'Collect Documents' },
    { id: 12, name: 'Daniel Moore', email: 'dmoore@email.com', phone: '(555) 234-8901', stage: 'Application', source: 'Referral - Bob Johnson', credit_score: 735, loan_amount: 455000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 18 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 91, next_action: 'Review Application' },
    { id: 13, name: 'Patricia Thompson', email: 'pthompson@email.com', phone: '(555) 345-9012', stage: 'Pre-Approved', source: 'Facebook', credit_score: 740, loan_amount: 575000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 21 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 94, next_action: 'House Hunting' },
    { id: 14, name: 'Kevin White', email: 'kwhite@email.com', phone: '(555) 456-0123', stage: 'Pre-Approved', source: 'Website', credit_score: 708, loan_amount: 410000, property_type: 'Condo', created_at: new Date(currentDate.getTime() - 24 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 86, next_action: 'Check-in Weekly' },
    { id: 15, name: 'Nancy Harris', email: 'nharris@email.com', phone: '(555) 567-1234', stage: 'Withdrawn', source: 'Zillow', credit_score: 690, loan_amount: 325000, property_type: 'Townhouse', created_at: new Date(currentDate.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 45, next_action: 'None', withdrawal_reason: 'Found another lender' },
    { id: 16, name: 'Brian Clark', email: 'bclark@email.com', phone: '(555) 678-2345', stage: 'Does Not Qualify', source: 'Social Media', credit_score: 580, loan_amount: 285000, property_type: 'Single Family', created_at: new Date(currentDate.getTime() - 35 * 24 * 60 * 60 * 1000).toISOString(), ai_score: 30, next_action: 'Credit Repair Referral', disqualification_reason: 'Credit score too low' },
  ];
};
