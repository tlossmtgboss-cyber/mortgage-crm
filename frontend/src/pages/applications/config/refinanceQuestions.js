/**
 * Refinance Application Questions Configuration
 * Defines all questions for the refinance mortgage application
 */

import {
  QuestionTypes,
  creditQuestions,
  incomeQuestions,
  governmentMonitoringQuestions,
  scheduleQuestions,
  authorizationsQuestions,
} from './purchaseQuestions';

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

// STAGE 5: INCOME — imported from purchaseQuestions.js (identical questions)
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

// STAGES 9-11: Government Monitoring, Schedule, Authorizations
// imported from purchaseQuestions.js (identical questions)

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
