/**
 * Refinance Application Questions Configuration
 * Defines all questions for the refinance mortgage application
 */

import { QuestionTypes, creditQuestions } from './purchaseQuestions';

// ============================================
// STAGE 1: ABOUT YOU
// ============================================
export const aboutYouQuestions = [
  // Veteran Status
  {
    id: 'veteran_status',
    stage: 'about_you',
    question: 'Have you or your spouse ever served in the U.S. military?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'veteran', label: 'Yes, I am a veteran', icon: 'medal' },
      { value: 'active_duty', label: 'Yes, currently serving', icon: 'shield' },
      { value: 'spouse_veteran', label: 'My spouse is a veteran', icon: 'users' },
      { value: 'no', label: 'No military service', icon: 'x' },
    ],
    required: true,
    helpText: 'Veterans may qualify for VA loans with no down payment',
    order: 1,
  },
  {
    id: 'va_benefit_used',
    stage: 'about_you',
    question: 'Have you used your VA home loan benefit before?',
    type: QuestionTypes.BOOLEAN,
    showIf: { veteran_status: ['veteran', 'active_duty', 'spouse_veteran'] },
    order: 2,
  },
  {
    id: 'va_disability_rating',
    stage: 'about_you',
    question: 'Do you have a VA disability rating?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'none', label: 'No disability rating' },
      { value: '10_plus', label: '10% or higher' },
      { value: 'purple_heart', label: 'Purple Heart recipient' },
    ],
    showIf: { veteran_status: ['veteran', 'active_duty'] },
    helpText: 'Veterans with 10%+ disability may be exempt from the VA funding fee',
    order: 3,
  },

  // Borrower Count
  {
    id: 'borrower_count',
    stage: 'about_you',
    question: 'How many people are on the current mortgage?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: '1', label: 'Just me', icon: 'user' },
      { value: '2', label: 'Two of us', icon: 'users' },
      { value: '3', label: 'Three people', icon: 'users' },
      { value: '4+', label: 'Four or more', icon: 'users' },
    ],
    required: true,
    order: 4,
  },
  {
    id: 'co_borrower_relationship',
    stage: 'about_you',
    question: 'What is your relationship to the co-borrower?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'spouse', label: 'Spouse' },
      { value: 'partner', label: 'Domestic Partner' },
      { value: 'relative', label: 'Family Member' },
      { value: 'friend', label: 'Friend' },
      { value: 'other', label: 'Other' },
    ],
    showIf: { borrower_count: ['2', '3', '4+'] },
    order: 5,
  },

  // Personal Information (borrower-specific)
  {
    id: 'first_name',
    stage: 'about_you',
    question: "What's your first name?",
    type: QuestionTypes.TEXT,
    placeholder: 'First name',
    required: true,
    borrowerSpecific: true,
    order: 6,
  },
  {
    id: 'middle_name',
    stage: 'about_you',
    question: 'Middle name (optional)',
    type: QuestionTypes.TEXT,
    placeholder: 'Middle name',
    required: false,
    borrowerSpecific: true,
    order: 7,
  },
  {
    id: 'last_name',
    stage: 'about_you',
    question: "What's your last name?",
    type: QuestionTypes.TEXT,
    placeholder: 'Last name',
    required: true,
    borrowerSpecific: true,
    order: 8,
  },
  {
    id: 'suffix',
    stage: 'about_you',
    question: 'Suffix (optional)',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: '', label: 'None' },
      { value: 'Jr', label: 'Jr.' },
      { value: 'Sr', label: 'Sr.' },
      { value: 'II', label: 'II' },
      { value: 'III', label: 'III' },
      { value: 'IV', label: 'IV' },
    ],
    required: false,
    borrowerSpecific: true,
    order: 9,
  },
  {
    id: 'email',
    stage: 'about_you',
    question: "What's your email address?",
    type: QuestionTypes.EMAIL,
    placeholder: 'you@example.com',
    required: true,
    borrowerSpecific: true,
    helpText: "We'll send your loan updates here",
    // Enable email validation with typo detection and carrier lookup
    validation: {
      checkTypos: true,
      verifyDeliverable: true,
      crossReference: 'phone', // Cross-reference with phone for data consistency
    },
    order: 10,
  },
  {
    id: 'phone',
    stage: 'about_you',
    question: "What's your phone number?",
    type: QuestionTypes.PHONE,
    placeholder: '(555) 555-5555',
    required: true,
    borrowerSpecific: true,
    // Enable phone validation with carrier lookup
    validation: {
      checkFormat: true,
      lookupCarrier: true,
      crossReference: 'email', // Cross-reference with email for data consistency
    },
    order: 11,
  },
  {
    id: 'date_of_birth',
    stage: 'about_you',
    question: "What's your date of birth?",
    type: QuestionTypes.DATE,
    placeholder: 'MM/DD/YYYY',
    required: true,
    borrowerSpecific: true,
    order: 12,
  },
  {
    id: 'ssn',
    stage: 'about_you',
    question: "What's your Social Security Number?",
    type: QuestionTypes.SSN,
    placeholder: 'XXX-XX-XXXX',
    required: true,
    borrowerSpecific: true,
    helpText: 'Required for credit check and identity verification',
    order: 13,
  },

  // Citizenship
  {
    id: 'citizenship',
    stage: 'about_you',
    question: 'What is your citizenship status?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'us_citizen', label: 'U.S. Citizen' },
      { value: 'permanent_resident', label: 'Permanent Resident (Green Card)' },
      { value: 'non_permanent_resident', label: 'Non-Permanent Resident Alien' },
      { value: 'other', label: 'Other' },
    ],
    required: true,
    borrowerSpecific: true,
    order: 14,
  },
  {
    id: 'visa_type',
    stage: 'about_you',
    question: 'What type of visa do you have?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'h1b', label: 'H-1B' },
      { value: 'l1', label: 'L-1' },
      { value: 'e1_e2', label: 'E-1/E-2' },
      { value: 'o1', label: 'O-1' },
      { value: 'tn', label: 'TN' },
      { value: 'other', label: 'Other' },
    ],
    showIf: { citizenship: 'non_permanent_resident' },
    borrowerSpecific: true,
    order: 15,
  },

  // Marital Status
  {
    id: 'marital_status',
    stage: 'about_you',
    question: 'What is your marital status?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'single', label: 'Single' },
      { value: 'married', label: 'Married' },
      { value: 'separated', label: 'Separated' },
      { value: 'divorced', label: 'Divorced' },
      { value: 'widowed', label: 'Widowed' },
    ],
    required: true,
    borrowerSpecific: true,
    order: 16,
  },

  // Alimony/Child Support Questions (for divorced/separated applicants)
  {
    id: 'receiving_alimony_child_support',
    stage: 'about_you',
    question: 'Are you receiving alimony or child support?',
    type: QuestionTypes.BOOLEAN,
    showIf: (data, borrower) => ['divorced', 'separated'].includes(borrower.marital_status),
    borrowerSpecific: true,
    helpText: 'This income can help you qualify for a larger loan',
    order: 16.1,
  },
  {
    id: 'receiving_alimony_amount',
    stage: 'about_you',
    question: 'How much do you receive monthly?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => ['divorced', 'separated'].includes(borrower.marital_status) && borrower.receiving_alimony_child_support === true,
    borrowerSpecific: true,
    order: 16.2,
  },
  {
    id: 'paying_alimony_child_support',
    stage: 'about_you',
    question: 'Are you paying alimony or child support?',
    type: QuestionTypes.BOOLEAN,
    showIf: (data, borrower) => ['divorced', 'separated'].includes(borrower.marital_status),
    borrowerSpecific: true,
    helpText: 'This obligation will be considered in your debt-to-income ratio',
    order: 16.3,
  },
  {
    id: 'paying_alimony_amount',
    stage: 'about_you',
    question: 'How much do you pay monthly?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => ['divorced', 'separated'].includes(borrower.marital_status) && borrower.paying_alimony_child_support === true,
    borrowerSpecific: true,
    order: 16.4,
  },

  {
    id: 'dependents_count',
    stage: 'about_you',
    question: 'How many dependents do you have?',
    type: QuestionTypes.NUMBER,
    placeholder: '0',
    min: 0,
    max: 20,
    borrowerSpecific: true,
    order: 17,
  },
  {
    id: 'dependents_ages',
    stage: 'about_you',
    question: 'What are the ages of your dependents?',
    type: QuestionTypes.TEXT,
    placeholder: 'e.g., 5, 8, 12',
    showIf: (data, borrower) => (borrower.dependents_count || 0) > 0,
    borrowerSpecific: true,
    order: 18,
  },
];

// ============================================
// STAGE 2: CURRENT MORTGAGE
// ============================================
export const currentMortgageQuestions = [
  {
    id: 'refinance_purpose',
    stage: 'current_mortgage',
    question: 'What is your goal for refinancing?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'lower_rate', label: 'Lower my interest rate', icon: 'trending-down' },
      { value: 'lower_payment', label: 'Lower my monthly payment', icon: 'dollar' },
      { value: 'cash_out', label: 'Cash out equity', icon: 'cash' },
      { value: 'shorter_term', label: 'Shorten loan term', icon: 'clock' },
      { value: 'remove_pmi', label: 'Remove mortgage insurance', icon: 'shield' },
      { value: 'remove_person', label: 'Remove someone from loan', icon: 'user-minus' },
    ],
    required: true,
    order: 1,
  },
  {
    id: 'cash_out_amount',
    stage: 'current_mortgage',
    question: 'How much cash would you like to take out?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { refinance_purpose: 'cash_out' },
    required: true,
    helpText: 'This is the amount of equity you want to access',
    order: 2,
  },
  {
    id: 'cash_out_purpose',
    stage: 'current_mortgage',
    question: 'What will you use the cash for?',
    type: QuestionTypes.MULTI_CHOICE,
    options: [
      { value: 'home_improvement', label: 'Home Improvement' },
      { value: 'debt_consolidation', label: 'Debt Consolidation' },
      { value: 'investment', label: 'Investment' },
      { value: 'education', label: 'Education Expenses' },
      { value: 'emergency_fund', label: 'Emergency Fund' },
      { value: 'other', label: 'Other' },
    ],
    showIf: { refinance_purpose: 'cash_out' },
    order: 3,
  },
  {
    id: 'current_lender',
    stage: 'current_mortgage',
    question: 'Who is your current mortgage lender?',
    type: QuestionTypes.TEXT,
    placeholder: 'e.g., Wells Fargo, Chase, etc.',
    required: true,
    order: 4,
  },
  {
    id: 'current_loan_balance',
    stage: 'current_mortgage',
    question: "What's your current loan balance?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    required: true,
    helpText: 'You can find this on your most recent mortgage statement',
    order: 6,
  },
  {
    id: 'current_interest_rate',
    stage: 'current_mortgage',
    question: "What's your current interest rate?",
    type: QuestionTypes.PERCENTAGE,
    placeholder: '0.00%',
    required: true,
    order: 7,
  },
  {
    id: 'current_mortgage_payment',
    stage: 'current_mortgage',
    question: "What's your current monthly mortgage payment?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    required: true,
    helpText: 'Include principal, interest, taxes, and insurance (PITI)',
    order: 8,
  },
  {
    id: 'current_loan_type',
    stage: 'current_mortgage',
    question: 'What type of loan do you currently have?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'conventional', label: 'Conventional' },
      { value: 'fha', label: 'FHA' },
      { value: 'va', label: 'VA' },
      { value: 'usda', label: 'USDA' },
      { value: 'jumbo', label: 'Jumbo' },
      { value: 'unknown', label: "I'm not sure" },
    ],
    required: true,
    order: 9,
  },
  {
    id: 'has_second_mortgage',
    stage: 'current_mortgage',
    question: 'Do you have a second mortgage or HELOC?',
    type: QuestionTypes.BOOLEAN,
    helpText: 'This includes home equity loans or lines of credit',
    order: 14,
  },
];

// ============================================
// STAGE 3: SECOND MORTGAGE (Conditional)
// ============================================
export const secondMortgageQuestions = [
  {
    id: 'second_mortgage_type',
    stage: 'second_mortgage',
    question: 'What type of second mortgage do you have?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'heloc', label: 'HELOC (Home Equity Line of Credit)' },
      { value: 'home_equity_loan', label: 'Home Equity Loan' },
      { value: 'second_mortgage', label: 'Second Mortgage' },
    ],
    showIf: { has_second_mortgage: true },
    required: true,
    order: 1,
  },
  {
    id: 'second_mortgage_lender',
    stage: 'second_mortgage',
    question: 'Who is the lender for your second mortgage?',
    type: QuestionTypes.TEXT,
    placeholder: 'Lender name',
    showIf: { has_second_mortgage: true },
    order: 2,
  },
  {
    id: 'second_mortgage_balance',
    stage: 'second_mortgage',
    question: "What's the current balance on your second mortgage?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { has_second_mortgage: true },
    required: true,
    order: 3,
  },
  {
    id: 'second_mortgage_payment',
    stage: 'second_mortgage',
    question: "What's your monthly payment on the second mortgage?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { has_second_mortgage: true },
    required: true,
    order: 5,
  },
  {
    id: 'second_mortgage_rate',
    stage: 'second_mortgage',
    question: "What's the interest rate on your second mortgage?",
    type: QuestionTypes.PERCENTAGE,
    placeholder: '0.00%',
    showIf: { has_second_mortgage: true },
    order: 6,
  },
  {
    id: 'payoff_second_mortgage',
    stage: 'second_mortgage',
    question: 'Do you want to pay off the second mortgage with this refinance?',
    type: QuestionTypes.BOOLEAN,
    showIf: { has_second_mortgage: true },
    helpText: 'This will consolidate your loans into one payment',
    order: 7,
  },
];

// ============================================
// STAGE 4: PROPERTY
// ============================================
export const propertyQuestions = [
  {
    id: 'property_address',
    stage: 'property',
    question: "What's your property address?",
    type: QuestionTypes.ADDRESS,
    required: true,
    helpText: 'Start typing to search for your address',
    order: 1,
  },
  {
    id: 'property_type',
    stage: 'property',
    question: 'What type of property is this?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'single_family', label: 'Single Family Home', icon: 'home' },
      { value: 'condo', label: 'Condominium', icon: 'building' },
      { value: 'townhouse', label: 'Townhouse', icon: 'townhouse' },
      { value: 'multi_family', label: 'Multi-Family (2-4 units)', icon: 'buildings' },
      { value: 'manufactured', label: 'Manufactured Home', icon: 'factory' },
    ],
    required: true,
    order: 2,
  },
  {
    id: 'property_use',
    stage: 'property',
    question: 'How do you use this property?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'primary_residence', label: 'Primary Residence', description: 'I live here full-time' },
      { value: 'second_home', label: 'Second Home', description: 'Vacation or part-time use' },
      { value: 'investment', label: 'Investment Property', description: "I rent it out" },
    ],
    required: true,
    order: 3,
  },
  {
    id: 'estimated_value',
    stage: 'property',
    question: "What's the estimated value of your home?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    required: true,
    helpText: 'Your best estimate based on recent sales or online valuations',
    order: 4,
  },
  {
    id: 'purchase_date',
    stage: 'property',
    question: 'When did you purchase this property?',
    type: QuestionTypes.DATE,
    placeholder: 'MM/DD/YYYY',
    required: true,
    order: 5,
  },
  {
    id: 'annual_property_tax',
    stage: 'property',
    question: "What's your annual property tax?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    helpText: 'Check your county tax bill or estimate',
    order: 7,
  },
  {
    id: 'annual_insurance',
    stage: 'property',
    question: "What's your annual homeowner's insurance premium?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    order: 8,
  },
  {
    id: 'has_hoa',
    stage: 'property',
    question: 'Is there a homeowners association (HOA)?',
    type: QuestionTypes.BOOLEAN,
    order: 9,
  },
  {
    id: 'hoa_monthly_fee',
    stage: 'property',
    question: "What's the monthly HOA fee?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { has_hoa: true },
    order: 10,
  },
  {
    id: 'solar_panels',
    stage: 'property',
    question: 'Does the property have solar panels?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'none', label: 'No solar panels' },
      { value: 'owned', label: 'Yes, owned outright' },
      { value: 'leased', label: 'Yes, leased' },
      { value: 'pace', label: 'Yes, financed through PACE' },
    ],
    order: 11,
  },
  {
    id: 'solar_monthly_payment',
    stage: 'property',
    question: 'What is the monthly solar payment?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { solar_panels: ['leased', 'pace'] },
    order: 12,
  },
];

// ============================================
// STAGE 5: INCOME
// ============================================
export const incomeQuestions = [
  {
    id: 'employment_status',
    stage: 'income',
    question: "What's your current employment status?",
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'employed', label: 'Employed (W-2)', icon: 'briefcase' },
      { value: 'self_employed', label: 'Self-Employed', icon: 'store' },
      { value: '1099_contractor', label: '1099 Contractor', icon: 'document' },
      { value: 'retired', label: 'Retired', icon: 'umbrella' },
      { value: 'not_employed', label: 'Not Currently Employed', icon: 'pause' },
    ],
    required: true,
    borrowerSpecific: true,
    order: 1,
  },

  // W-2 Employee Questions
  {
    id: 'employer_name',
    stage: 'income',
    question: 'Who is your employer?',
    type: QuestionTypes.EMPLOYER,
    placeholder: 'Start typing employer name...',
    showIf: (data, borrower) => ['employed', '1099_contractor'].includes(borrower.employment_status),
    required: true,
    borrowerSpecific: true,
    helpText: 'Search for your employer or type it manually',
    order: 2,
  },
  {
    id: 'job_title',
    stage: 'income',
    question: "What's your job title?",
    type: QuestionTypes.TEXT,
    placeholder: 'e.g., Software Engineer',
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    required: true,
    borrowerSpecific: true,
    order: 3,
  },
  {
    id: 'employer_phone',
    stage: 'income',
    question: "What's your employer's phone number?",
    type: QuestionTypes.PHONE,
    placeholder: '(555) 555-5555',
    showIf: (data, borrower) => ['employed', '1099_contractor'].includes(borrower.employment_status),
    borrowerSpecific: true,
    autoPopulateFrom: { field: 'employer_name', property: 'phone' },
    order: 4,
  },
  {
    id: 'time_at_job',
    stage: 'income',
    question: 'How long have you worked there?',
    type: QuestionTypes.DURATION,
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    required: true,
    borrowerSpecific: true,
    helpText: 'Enter years and months',
    order: 5,
  },
  {
    id: 'years_in_profession',
    stage: 'income',
    question: 'How long have you been in this line of work?',
    type: QuestionTypes.DURATION,
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    borrowerSpecific: true,
    helpText: 'Enter years and months',
    order: 6,
  },
  {
    id: 'pay_type',
    stage: 'income',
    question: 'How are you paid?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'hourly', label: 'Hourly' },
      { value: 'salary', label: 'Salary' },
      { value: 'commission', label: '100% Commission' },
      { value: 'tips', label: 'Tips' },
      { value: 'other', label: 'Other' },
    ],
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    required: true,
    borrowerSpecific: true,
    order: 7,
  },
  {
    id: 'pay_type_other',
    stage: 'income',
    question: 'Please describe how you are paid',
    type: QuestionTypes.TEXT,
    placeholder: 'Describe your pay structure',
    showIf: (data, borrower) => borrower.employment_status === 'employed' && borrower.pay_type === 'other',
    required: true,
    borrowerSpecific: true,
    order: 8,
  },

  // Hourly pay questions
  {
    id: 'hourly_rate',
    stage: 'income',
    question: "What's your hourly rate?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0.00',
    showIf: (data, borrower) => borrower.employment_status === 'employed' && borrower.pay_type === 'hourly',
    required: true,
    borrowerSpecific: true,
    helpText: 'Enter your regular hourly pay rate',
    order: 8.1,
  },
  {
    id: 'hours_per_week',
    stage: 'income',
    question: 'How many hours do you work per week?',
    type: QuestionTypes.NUMBER,
    placeholder: '40',
    min: 1,
    max: 80,
    showIf: (data, borrower) => borrower.employment_status === 'employed' && borrower.pay_type === 'hourly',
    required: true,
    borrowerSpecific: true,
    helpText: 'Enter your standard weekly hours (not including overtime)',
    order: 8.2,
  },

  // Annual base income (only for non-hourly pay types)
  {
    id: 'annual_base_income',
    stage: 'income',
    question: "What's your annual base income?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.employment_status === 'employed' && borrower.pay_type !== 'hourly',
    required: true,
    borrowerSpecific: true,
    helpText: 'Enter your annual salary',
    order: 9,
  },
  {
    id: 'has_overtime',
    stage: 'income',
    question: 'Do you receive overtime pay?',
    type: QuestionTypes.BOOLEAN,
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    borrowerSpecific: true,
    order: 10,
  },
  {
    id: 'overtime_hours_weekly',
    stage: 'income',
    question: 'How many hours of overtime do you work weekly?',
    type: QuestionTypes.NUMBER,
    placeholder: '0',
    min: 0,
    max: 40,
    showIf: (data, borrower) => borrower.has_overtime === true,
    borrowerSpecific: true,
    helpText: 'Average weekly overtime hours',
    order: 10.1,
  },
  {
    id: 'has_bonus',
    stage: 'income',
    question: 'Do you receive annual bonuses?',
    type: QuestionTypes.BOOLEAN,
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    borrowerSpecific: true,
    order: 11,
  },
  {
    id: 'bonus_amount',
    stage: 'income',
    question: "What's your typical annual bonus?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.has_bonus === true,
    borrowerSpecific: true,
    order: 12,
  },
  {
    id: 'has_commission',
    stage: 'income',
    question: 'Do you earn commission income?',
    type: QuestionTypes.BOOLEAN,
    showIf: (data, borrower) => borrower.employment_status === 'employed',
    borrowerSpecific: true,
    order: 13,
  },
  {
    id: 'commission_amount',
    stage: 'income',
    question: "What's your typical annual commission?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.has_commission === true,
    borrowerSpecific: true,
    order: 14,
  },

  // Self-Employed Questions
  {
    id: 'business_name',
    stage: 'income',
    question: "What's your business name?",
    type: QuestionTypes.TEXT,
    placeholder: 'Business name',
    showIf: (data, borrower) => borrower.employment_status === 'self_employed',
    required: true,
    borrowerSpecific: true,
    order: 15,
  },
  {
    id: 'business_type',
    stage: 'income',
    question: 'What type of business is it?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'sole_proprietorship', label: 'Sole Proprietorship' },
      { value: 'llc', label: 'LLC' },
      { value: 's_corp', label: 'S Corporation' },
      { value: 'c_corp', label: 'C Corporation' },
      { value: 'partnership', label: 'Partnership' },
    ],
    showIf: (data, borrower) => borrower.employment_status === 'self_employed',
    required: true,
    borrowerSpecific: true,
    order: 16,
  },
  {
    id: 'business_ownership_percent',
    stage: 'income',
    question: 'What percentage of the business do you own?',
    type: QuestionTypes.PERCENTAGE,
    placeholder: '100%',
    showIf: (data, borrower) => borrower.employment_status === 'self_employed',
    required: true,
    borrowerSpecific: true,
    order: 17,
  },
  {
    id: 'years_in_business',
    stage: 'income',
    question: 'How long have you been self-employed?',
    type: QuestionTypes.NUMBER,
    placeholder: '0',
    min: 0,
    max: 50,
    showIf: (data, borrower) => borrower.employment_status === 'self_employed',
    required: true,
    borrowerSpecific: true,
    helpText: 'Most loans require at least 2 years of self-employment',
    order: 18,
  },
  {
    id: 'annual_self_employment_income',
    stage: 'income',
    question: "What's your annual income from self-employment?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.employment_status === 'self_employed',
    required: true,
    borrowerSpecific: true,
    helpText: 'Use your net income from tax returns',
    order: 19,
  },

  // Retired Questions
  {
    id: 'retirement_income_type',
    stage: 'income',
    question: 'What are your sources of retirement income?',
    type: QuestionTypes.MULTI_CHOICE,
    options: [
      { value: 'social_security', label: 'Social Security' },
      { value: 'pension', label: 'Pension' },
      { value: '401k_ira', label: '401(k)/IRA Distributions' },
      { value: 'annuity', label: 'Annuity' },
      { value: 'investment', label: 'Investment Income' },
      { value: 'other', label: 'Other' },
    ],
    showIf: (data, borrower) => borrower.employment_status === 'retired',
    required: true,
    borrowerSpecific: true,
    order: 20,
  },
  {
    id: 'monthly_retirement_income',
    stage: 'income',
    question: "What's your total monthly retirement income?",
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.employment_status === 'retired',
    required: true,
    borrowerSpecific: true,
    order: 21,
  },

  // Additional Income
  {
    id: 'has_additional_income',
    stage: 'income',
    question: 'Do you have any additional income sources?',
    type: QuestionTypes.BOOLEAN,
    borrowerSpecific: true,
    order: 22,
  },
  {
    id: 'additional_income_type',
    stage: 'income',
    question: 'What type of additional income?',
    type: QuestionTypes.MULTI_CHOICE,
    options: [
      { value: 'rental', label: 'Rental Income' },
      { value: 'alimony', label: 'Alimony/Child Support Received' },
      { value: 'side_business', label: 'Side Business' },
      { value: 'investment', label: 'Investment/Dividend Income' },
      { value: 'part_time', label: 'Part-Time Job' },
      { value: 'other', label: 'Other' },
    ],
    showIf: (data, borrower) => borrower.has_additional_income === true,
    borrowerSpecific: true,
    order: 23,
  },
  {
    id: 'additional_income_amount',
    stage: 'income',
    question: 'Monthly amount from additional income:',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data, borrower) => borrower.has_additional_income === true,
    borrowerSpecific: true,
    order: 24,
  },
];

// ============================================
// STAGE 6: ASSETS
// ============================================
export const assetsQuestions = [
  {
    id: 'checking_balance',
    stage: 'assets',
    question: 'Total in checking accounts:',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    required: true,
    order: 1,
  },
  {
    id: 'savings_balance',
    stage: 'assets',
    question: 'Total in savings accounts:',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    order: 2,
  },
  {
    id: 'retirement_balance',
    stage: 'assets',
    question: 'Total in retirement accounts (401k, IRA, etc.):',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    order: 3,
  },
  {
    id: 'investment_balance',
    stage: 'assets',
    question: 'Total in investment/brokerage accounts:',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    order: 4,
  },
  {
    id: 'other_assets',
    stage: 'assets',
    question: 'Other liquid assets (stocks, bonds, CDs):',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    order: 5,
  },
];

// ============================================
// STAGE 7: REAL ESTATE OWNED
// ============================================
export const realEstateOwnedQuestions = [
  {
    id: 'owns_other_property',
    stage: 'real_estate_owned',
    question: 'Do you own any other real estate besides the property being refinanced?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 1,
  },
  {
    id: 'other_property_count',
    stage: 'real_estate_owned',
    question: 'How many other properties do you own?',
    type: QuestionTypes.NUMBER,
    placeholder: '0',
    min: 1,
    max: 20,
    showIf: { owns_other_property: true },
    order: 2,
  },
  {
    id: 'reo_mortgage_statement',
    stage: 'real_estate_owned',
    question: 'Upload a mortgage statement for your other property',
    type: QuestionTypes.FILE_UPLOAD,
    showIf: { owns_other_property: true },
    acceptedTypes: ['.pdf', '.jpg', '.jpeg', '.png'],
    maxSize: 10, // MB
    helpText: 'Upload your most recent mortgage statement. We will extract the property details automatically.',
    parseDocument: true,
    documentType: 'mortgage_statement',
    order: 3,
  },
  {
    id: 'reo_property_address',
    stage: 'real_estate_owned',
    question: 'What is the address of this property?',
    type: QuestionTypes.ADDRESS,
    showIf: { owns_other_property: true },
    required: true,
    autoPopulateFrom: { field: 'reo_mortgage_statement', property: 'property_address' },
    helpText: 'Verify the address is correct',
    order: 4,
  },
  {
    id: 'reo_property_type',
    stage: 'real_estate_owned',
    question: 'What type of property is this?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'single_family', label: 'Single Family Home' },
      { value: 'condo', label: 'Condominium' },
      { value: 'townhouse', label: 'Townhouse' },
      { value: 'multi_family', label: 'Multi-Family (2-4 units)' },
      { value: 'commercial', label: 'Commercial' },
      { value: 'land', label: 'Land' },
    ],
    showIf: { owns_other_property: true },
    required: true,
    order: 5,
  },
  {
    id: 'reo_property_use',
    stage: 'real_estate_owned',
    question: 'How is this property used?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'primary_residence', label: 'Primary Residence' },
      { value: 'second_home', label: 'Second Home' },
      { value: 'investment', label: 'Investment/Rental Property' },
    ],
    showIf: { owns_other_property: true },
    required: true,
    order: 6,
  },
  {
    id: 'reo_market_value',
    stage: 'real_estate_owned',
    question: 'What is the estimated market value?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { owns_other_property: true },
    required: true,
    autoPopulateFrom: { field: 'reo_mortgage_statement', property: 'market_value' },
    helpText: 'Verify the value is accurate',
    order: 7,
  },
  {
    id: 'reo_mortgage_balance',
    stage: 'real_estate_owned',
    question: 'What is the current mortgage balance?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { owns_other_property: true },
    required: true,
    autoPopulateFrom: { field: 'reo_mortgage_statement', property: 'loan_balance' },
    helpText: 'Verify the balance is correct',
    order: 8,
  },
  {
    id: 'reo_monthly_payment',
    stage: 'real_estate_owned',
    question: 'What is the monthly mortgage payment?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: { owns_other_property: true },
    required: true,
    autoPopulateFrom: { field: 'reo_mortgage_statement', property: 'monthly_payment' },
    helpText: 'Include principal, interest, taxes, and insurance',
    order: 9,
  },
  {
    id: 'reo_rental_income',
    stage: 'real_estate_owned',
    question: 'What is the monthly rental income from this property?',
    type: QuestionTypes.CURRENCY,
    placeholder: '$0',
    showIf: (data) => data.owns_other_property === true && data.reo_property_use === 'investment',
    helpText: 'Enter gross monthly rent collected',
    order: 10,
  },
  {
    id: 'reo_info_accurate',
    stage: 'real_estate_owned',
    question: 'Please confirm the property information above is accurate',
    type: QuestionTypes.BOOLEAN,
    showIf: { owns_other_property: true },
    required: true,
    helpText: 'By confirming, you certify that the real estate information provided is correct to the best of your knowledge.',
    order: 11,
  },
];

// ============================================
// STAGE 8: BACKGROUND (Declarations)
// ============================================
export const backgroundQuestions = [
  {
    id: 'has_outstanding_judgments',
    stage: 'background',
    question: 'Are there any outstanding judgments against you?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 1,
  },
  {
    id: 'has_bankruptcy',
    stage: 'background',
    question: 'Have you declared bankruptcy in the past 7 years?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 2,
  },
  {
    id: 'bankruptcy_type',
    stage: 'background',
    question: 'What type of bankruptcy?',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'chapter_7', label: 'Chapter 7' },
      { value: 'chapter_13', label: 'Chapter 13' },
      { value: 'chapter_11', label: 'Chapter 11' },
      { value: 'chapter_12', label: 'Chapter 12' },
    ],
    showIf: { has_bankruptcy: true },
    order: 3,
  },
  {
    id: 'bankruptcy_discharge_date',
    stage: 'background',
    question: 'When was the bankruptcy discharged?',
    type: QuestionTypes.DATE,
    placeholder: 'MM/DD/YYYY',
    showIf: { has_bankruptcy: true },
    order: 4,
  },
  {
    id: 'has_foreclosure',
    stage: 'background',
    question: 'Have you had a property foreclosed in the past 7 years?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 5,
  },
  {
    id: 'foreclosure_date',
    stage: 'background',
    question: 'When did the foreclosure occur?',
    type: QuestionTypes.DATE,
    placeholder: 'MM/DD/YYYY',
    showIf: { has_foreclosure: true },
    order: 6,
  },
  {
    id: 'has_lawsuit',
    stage: 'background',
    question: 'Are you a party to any lawsuit?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 7,
  },
  {
    id: 'has_delinquent_debt',
    stage: 'background',
    question: 'Are you delinquent on any federal debt?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    helpText: 'Student loans, tax liens, etc.',
    order: 8,
  },
  // Note: Alimony/child support questions moved to about_you stage for divorced/separated applicants
  {
    id: 'is_co_signer',
    stage: 'background',
    question: 'Are you a co-signer on any other debt?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 11,
  },
  {
    id: 'is_us_citizen',
    stage: 'background',
    question: 'Are you a U.S. citizen?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    order: 12,
  },
  {
    id: 'will_continue_to_occupy',
    stage: 'background',
    question: 'Will you continue to occupy the property as your primary residence?',
    type: QuestionTypes.BOOLEAN,
    required: true,
    showIf: { property_use: 'primary_residence' },
    order: 13,
  },
];

// ============================================
// STAGE 9: GOVERNMENT MONITORING (HMDA)
// ============================================
export const governmentMonitoringQuestions = [
  {
    id: 'hmda_intro',
    stage: 'government_monitoring',
    question: 'Government Monitoring Information',
    type: QuestionTypes.INFO, // Display only - no input
    infoText: 'The following information is requested by the federal government to monitor compliance with federal statutes. You are not required to furnish this information, but are encouraged to do so.',
    infoStyle: { fontSize: '16px', lineHeight: '1.6', fontWeight: '400' },
    order: 1,
  },
  {
    id: 'ethnicity',
    stage: 'government_monitoring',
    question: 'Ethnicity (optional)',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'hispanic_latino', label: 'Hispanic or Latino' },
      { value: 'not_hispanic_latino', label: 'Not Hispanic or Latino' },
      { value: 'prefer_not_to_say', label: 'I do not wish to provide this information' },
    ],
    required: false,
    borrowerSpecific: true,
    order: 2,
  },
  {
    id: 'race',
    stage: 'government_monitoring',
    question: 'Race (optional)',
    type: QuestionTypes.MULTI_CHOICE,
    options: [
      { value: 'american_indian', label: 'American Indian or Alaska Native' },
      { value: 'asian', label: 'Asian' },
      { value: 'black', label: 'Black or African American' },
      { value: 'pacific_islander', label: 'Native Hawaiian or Other Pacific Islander' },
      { value: 'white', label: 'White' },
      { value: 'prefer_not_to_say', label: 'I do not wish to provide this information' },
    ],
    required: false,
    borrowerSpecific: true,
    order: 3,
  },
  {
    id: 'sex',
    stage: 'government_monitoring',
    question: 'Sex (optional)',
    type: QuestionTypes.SINGLE_CHOICE,
    options: [
      { value: 'female', label: 'Female' },
      { value: 'male', label: 'Male' },
      { value: 'prefer_not_to_say', label: 'I do not wish to provide this information' },
    ],
    required: false,
    borrowerSpecific: true,
    order: 4,
  },
];

// ============================================
// STAGE 10: SCHEDULE
// ============================================
export const scheduleQuestions = [
  {
    id: 'consultation_appointment',
    stage: 'schedule',
    question: 'Schedule your consultation',
    type: QuestionTypes.CALENDAR_SCHEDULER,
    helpText: 'Select a date and time that works best for you to speak with a loan officer.',
    appointmentType: 'consultation',
    duration: 30, // 30 minutes
    required: false,
    order: 1,
  },
];

// ============================================
// STAGE 11: AUTHORIZATIONS
// ============================================
export const authorizationsQuestions = [
  {
    id: 'econsent_agreed',
    stage: 'authorizations',
    question: 'Electronic Consent',
    type: QuestionTypes.ECONSENT,
    required: true,
    defaultValue: false, // Consent must require affirmative action
    allowChoice: true, // Allow user to choose between agree/disagree
    // Full eConsent verbiage
    eConsentContent: {
      intro: `To use electronic signatures and receive documents electronically in connection with your use of this platform, you must read and consent to the terms outlined in this document, which require your ability to access and retain electronic documents.`,
      sections: [
        {
          title: null,
          content: `This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing notices, and any other loan documents that we provide to you in electronic form.

If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in other portals, and/or through other methods we may use for delivery of electronic Documents. With Your eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper. Anytime you are signing using a platform contracted with nCino Mortgage, you will be prompted to provide eConsent again.

Before We can engage in this transaction electronically, it is important that You understand Your rights and responsibilities. Please read the following and affirm Your consent to conduct business with Us electronically. For purposes of this eConsent Agreement, 'You' and 'Your' mean the borrower(s) under the applicable loan to which such Documents apply, and 'We', 'Our' and 'Us' mean the applicable mortgage broker(s), loan processor(s), or mortgage banker(s) with whom You are transacting business for such loan(s).`
        },
        {
          title: 'Your Consent',
          content: `Your consent to participate in this transaction electronically will apply to all Loan Documents for the applicable loans for which You are applying. If You provide Your consent by clicking the 'I agree' button at the bottom of the page, We will conduct this transaction electronically, instead of providing You with the Loan Documents in paper form.

If a document related to Your loan is not available in electronic form, a paper copy will be provided to You free of charge.

Conducting this transaction electronically is an option. If You choose not to receive Documents electronically, paper Documents will be mailed to You. Additionally: You will not be required to pay a fee for receiving paper copies of the Documents.`
        },
        {
          title: 'Withdrawal of Consent',
          content: `You have the right to withdraw Your consent at any time. By declining or revoking Your consent to receive Documents electronically, We will provide You with the Documents in paper form.

If You originally consent to receive Documents electronically, but later decide to withdraw Your consent, You can do so by clicking on the 'I do not agree' button, or by contacting Us by phone.

If You originally consent to receive Documents electronically, but later withdraw Your consent, You will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.`
        },
        {
          title: 'Obtaining Paper Copies',
          content: `After Your consent is given, You may request from Us paper copies of Your Loan Documents by contacting Us. If You request paper copies of the Loan Documents, You will not be required to pay a fee for receiving paper copies of the Loan Documents.`
        },
        {
          title: 'System Requirements',
          content: `In order to receive Documents electronically, You must have a computer with Internet access and an Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in order to keep copies of Your Documents electronically for Your records.

If the software or hardware requirements change in the future, and You are unable to continue receiving Documents electronically, paper copies of such Loan Documents will be mailed to You once You notify Us that You are no longer able to access the Documents electronically because of the changed requirements. We will use commercially reasonable efforts to notify You before such requirements change. If You choose to withdraw Your consent upon notification of the change, You will be able to do so without penalty.`
        },
        {
          title: 'How Can We Reach You',
          content: `You must promptly notify Us if there is a change in Your email address or in other information needed to contact You electronically.

We will not assume liability for non-receipt of notification of the availability of Documents electronically in the event Your email address on file is invalid; Your email or Internet service provider filters the notification as 'spam' or 'junk mail'; there is a malfunction in Your computer, browser, Internet service and/or software; or for other reasons beyond Our control.`
        }
      ]
    },
    order: 1,
  },
  {
    id: 'credit_auth_agreed',
    stage: 'authorizations',
    question: 'Credit Authorization',
    type: QuestionTypes.CREDIT_AUTH,
    required: true,
    defaultValue: false, // Consent must require affirmative action
    allowChoice: true, // Allow user to choose between agree/disagree
    // Full Credit Authorization verbiage
    creditAuthContent: {
      intro: `Your credit information will help us understand more about your personal and financial background and ensure we give you the most accurate mortgage options. To help us, we need the following authorization:`,
      authorization: `I authorize my Lender to perform a credit check, via either a soft or hard pull of my credit; I understand this may affect my credit score. I acknowledge that any owner of a completed loan, its servicers, successors and assigns, may verify or re-verify any information contained in this form or obtain any information or data relating to a completed loan, for any legitimate purpose, through any source, including a source named in this form or a consumer reporting agency.`
    },
    order: 2,
  },
];

// ============================================
// EXPORT ALL QUESTIONS
// ============================================
export const allRefinanceQuestions = [
  ...aboutYouQuestions,
  ...currentMortgageQuestions,
  ...secondMortgageQuestions,
  ...propertyQuestions,
  ...incomeQuestions,
  ...assetsQuestions,
  ...realEstateOwnedQuestions,
  ...creditQuestions,
  ...backgroundQuestions,
  ...governmentMonitoringQuestions,
  ...scheduleQuestions,
  ...authorizationsQuestions,
].sort((a, b) => {
  // Sort by stage order first, then by question order
  const stageOrder = {
    about_you: 1,
    current_mortgage: 2,
    second_mortgage: 3,
    property: 4,
    income: 5,
    assets: 6,
    real_estate_owned: 7,
    credit: 8,
    background: 9,
    government_monitoring: 10,
    schedule: 11,
    authorizations: 12,
  };

  const stageA = stageOrder[a.stage] || 99;
  const stageB = stageOrder[b.stage] || 99;

  if (stageA !== stageB) return stageA - stageB;
  return (a.order || 99) - (b.order || 99);
});

// Get questions by stage
export function getQuestionsByStage(stageId) {
  return allRefinanceQuestions.filter(q => q.stage === stageId);
}

export default allRefinanceQuestions;
