// Fallback milestone/task data used when AI parsing fails
export const FALLBACK_MILESTONES = [
  {
    name: 'New Lead',
    tasks: [
      { name: 'Log lead in CRM', owner: 'Concierge', sla: 15, slaUnit: 'hours', aiAuto: true },
      { name: 'Initial contact via phone/email', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
      { name: 'Send welcome email with company overview', owner: 'Concierge', sla: 1, slaUnit: 'hours', aiAuto: true },
      { name: 'Schedule discovery call', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Conduct needs assessment call', owner: 'Loan Officer', sla: 48, slaUnit: 'hours', aiAuto: false },
      { name: 'Send pre-qualification questionnaire', owner: 'Concierge', sla: 4, slaUnit: 'hours', aiAuto: true },
      { name: 'Review pre-qualification responses', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Request credit pull authorization', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Pull credit report', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Analyze credit report', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Review credit disputes if needed', owner: 'Loan Officer', sla: 48, slaUnit: 'hours', aiAuto: false },
      { name: 'Request income documentation preview', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Provide initial loan estimate', owner: 'Loan Officer', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Send product comparison sheet', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Schedule product selection meeting', owner: 'Concierge', sla: 2, slaUnit: 'days', aiAuto: true },
      { name: 'Assign to loan team', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false }
    ]
  },
  {
    name: 'Application',
    tasks: [
      { name: 'Send application portal link', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
      { name: 'Provide application tutorial video', owner: 'Concierge', sla: 1, slaUnit: 'hours', aiAuto: true },
      { name: 'Monitor application progress', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Send application completion reminders', owner: 'Concierge', sla: 48, slaUnit: 'hours', aiAuto: true },
      { name: 'Review completed application', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Verify application accuracy', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Request missing application information', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: true },
      { name: 'Generate initial disclosures', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Send initial disclosures to borrower', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
      { name: 'Confirm disclosure receipt', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Log intent to proceed', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Lock interest rate if requested', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: false },
      { name: 'Send rate lock confirmation', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
      { name: 'Create initial document checklist', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Send document request to borrower', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true }
    ]
  },
  {
    name: 'Processing',
    tasks: [
      { name: 'Review all uploaded documents', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Verify income documents (paystubs)', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Verify employment (VOE)', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Request W2s for past 2 years', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Request tax returns if self-employed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Verify asset accounts (bank statements)', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Source large deposits if needed', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Review gift funds documentation', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Order appraisal', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Collect appraisal fee', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Schedule appraisal appointment', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
      { name: 'Monitor appraisal status', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: true },
      { name: 'Review appraisal report', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Share appraisal with borrower', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Order title search', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Review preliminary title report', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Clear title exceptions if needed', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: false },
      { name: 'Order homeowners insurance', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
      { name: 'Verify insurance coverage amounts', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Obtain mortgage insurance quote if needed', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Request HOA documents if applicable', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
      { name: 'Review HOA budget and bylaws', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Order flood certification', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Order flood insurance if required', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
      { name: 'Prepare file for underwriting', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Complete loan application package', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false }
    ]
  },
  {
    name: 'Underwriting',
    tasks: [
      { name: 'Submit file to underwriter', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Confirm underwriter assignment', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Monitor underwriting queue', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Receive initial underwriting decision', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Review underwriting conditions', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Explain conditions to borrower', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Request additional documentation for conditions', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Review updated bank statements', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Obtain updated paystub', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Request letter of explanation if needed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Verify employment again (72hr prior to close)', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Clear PTD conditions', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Submit cleared conditions to UW', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Receive final approval', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Review final approval conditions', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Notify borrower of approval', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: true },
      { name: 'Order final title update', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false }
    ]
  },
  {
    name: 'Clear to Close',
    tasks: [
      { name: 'Receive clear to close from UW', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Notify loan team of CTC', owner: 'Processor', sla: 2, slaUnit: 'hours', aiAuto: true },
      { name: 'Request final Closing Disclosure figures', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Prepare Closing Disclosure', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Send initial CD to borrower', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: true },
      { name: 'Confirm CD receipt and review', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Wait 3-day CD review period', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Coordinate closing date/time with title', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Coordinate with borrower schedule', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Confirm closing appointment', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Send closing location details', owner: 'Concierge', sla: 48, slaUnit: 'hours', aiAuto: true },
      { name: 'Verify wiring instructions if needed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Send pre-closing checklist to borrower', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
      { name: 'Verify final insurance binder', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Order final verification of employment', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Perform final credit check', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Send final figures to title company', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Review final CD for accuracy', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Send final CD if changes occurred', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true }
    ]
  },
  {
    name: 'Closing',
    tasks: [
      { name: 'Send closing package to title', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
      { name: 'Review closing package for accuracy', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Send closing reminder to borrower', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Verify borrower has required IDs', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Verify cash to close amount', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Confirm wire/cashier check instructions', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
      { name: 'Monitor closing appointment', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: false },
      { name: 'Receive signed closing documents', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Review closing documents for completeness', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Submit docs for funding approval', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
      { name: 'Receive funding approval', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
      { name: 'Wire funds to title company', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: false },
      { name: 'Confirm funding with title', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
      { name: 'Notify borrower of successful funding', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: true },
      { name: 'Send congratulations package', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
      { name: 'Request closing gift preference', owner: 'Concierge', sla: 2, slaUnit: 'days', aiAuto: true },
      { name: 'Send closing gift', owner: 'Concierge', sla: 5, slaUnit: 'days', aiAuto: false }
    ]
  },
  {
    name: 'Post-Close',
    tasks: [
      { name: 'Archive loan file', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
      { name: 'Upload to investor portal if sold', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: false },
      { name: 'Send welcome to servicing email', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
      { name: 'Provide servicing contact info', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
      { name: '7-day check-in call', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
      { name: 'Request Google review', owner: 'Concierge', sla: 10, slaUnit: 'days', aiAuto: true },
      { name: 'Request Zillow review', owner: 'Concierge', sla: 10, slaUnit: 'days', aiAuto: true },
      { name: 'Add to referral partner list', owner: 'Loan Officer', sla: 14, slaUnit: 'days', aiAuto: false },
      { name: '30-day check-in call', owner: 'Loan Officer', sla: 30, slaUnit: 'days', aiAuto: true },
      { name: 'Send first mortgage statement guide', owner: 'Concierge', sla: 30, slaUnit: 'days', aiAuto: true },
      { name: 'Schedule quarterly check-in', owner: 'Concierge', sla: 60, slaUnit: 'days', aiAuto: true },
      { name: 'Add to birthday calendar', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
      { name: 'Add to home anniversary calendar', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true }
    ]
  },
  {
    name: 'Client for Life',
    tasks: [
      { name: 'Send quarterly market update', owner: 'Concierge', sla: 90, slaUnit: 'days', aiAuto: true },
      { name: 'Monitor for refinance opportunities', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: true },
      { name: 'Send home anniversary card', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
      { name: 'Send birthday card/gift', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
      { name: 'Annual financial review invitation', owner: 'Concierge', sla: 330, slaUnit: 'days', aiAuto: true },
      { name: 'Conduct annual review call', owner: 'Loan Officer', sla: 365, slaUnit: 'days', aiAuto: false },
      { name: 'Review for equity opportunities', owner: 'Loan Officer', sla: 365, slaUnit: 'days', aiAuto: false },
      { name: 'Send holiday greetings', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
      { name: 'Check for life changes (marriage, kids, etc)', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: false },
      { name: 'Send home maintenance tips', owner: 'Concierge', sla: 120, slaUnit: 'days', aiAuto: true },
      { name: 'Provide property value updates', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: true },
      { name: 'Request referrals gently', owner: 'Loan Officer', sla: 90, slaUnit: 'days', aiAuto: false }
    ]
  }
];
