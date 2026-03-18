/**
 * PurchaseApplication - Shared Constants
 *
 * Stage definitions, declaration questions, planning questions,
 * and employer list used across the purchase application flow.
 */

export const STAGES = [
  { id: 'account', label: 'Get Started', icon: 'user', description: 'Create your account', hideFromProgress: true },
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions to personalize' },
  { id: 'planning', label: 'Your Goals', icon: 'goals', description: 'Mortgage preferences' },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics about you' },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn' },
  { id: 'assets', label: 'Your Assets', icon: 'assets', description: 'Down payment funds' },
  { id: 'property', label: 'New Home', icon: 'home', description: 'Property details' },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info' },
  { id: 'schedule', label: 'Schedule', icon: 'calendar', description: 'Book a call' },
];

// Visible stages for progress bar (excludes account creation)
export const VISIBLE_STAGES = STAGES.filter(s => !s.hideFromProgress);

// US States for dropdown
export const US_STATES = [
  { value: '', label: 'Select State...' },
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' }, { value: 'AZ', label: 'Arizona' },
  { value: 'AR', label: 'Arkansas' }, { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' }, { value: 'FL', label: 'Florida' },
  { value: 'GA', label: 'Georgia' }, { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' }, { value: 'IA', label: 'Iowa' },
  { value: 'KS', label: 'Kansas' }, { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' }, { value: 'MA', label: 'Massachusetts' },
  { value: 'MI', label: 'Michigan' }, { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' }, { value: 'NE', label: 'Nebraska' },
  { value: 'NV', label: 'Nevada' }, { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' }, { value: 'NC', label: 'North Carolina' },
  { value: 'ND', label: 'North Dakota' }, { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' }, { value: 'RI', label: 'Rhode Island' },
  { value: 'SC', label: 'South Carolina' }, { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' }, { value: 'VT', label: 'Vermont' },
  { value: 'VA', label: 'Virginia' }, { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' }, { value: 'DC', label: 'Washington DC' }
];

// Common employers for autocomplete
export const COMMON_EMPLOYERS = [
  'CMG Home Loans', 'CMG Financial', 'Wells Fargo', 'Bank of America', 'JPMorgan Chase',
  'Citibank', 'US Bank', 'PNC Bank', 'Capital One', 'TD Bank',
  'Amazon', 'Apple', 'Google', 'Microsoft', 'Meta', 'Netflix', 'Tesla',
  'Walmart', 'Target', 'Costco', 'Home Depot', 'Lowes',
  'UnitedHealth Group', 'CVS Health', 'Cigna', 'Anthem', 'Kaiser Permanente',
  'AT&T', 'Verizon', 'T-Mobile', 'Comcast', 'Charter Communications',
  'FedEx', 'UPS', 'USPS', 'DHL',
  'Boeing', 'Lockheed Martin', 'Raytheon', 'Northrop Grumman',
  'General Motors', 'Ford', 'Toyota', 'Honda', 'BMW',
  'Starbucks', 'McDonalds', 'Chipotle', 'Subway',
  'United Airlines', 'Delta Airlines', 'American Airlines', 'Southwest Airlines',
  'Marriott', 'Hilton', 'Hyatt',
  'Disney', 'Warner Bros', 'NBC Universal', 'Paramount',
  'Deloitte', 'PwC', 'EY', 'KPMG', 'Accenture', 'McKinsey',
  'IBM', 'Oracle', 'Salesforce', 'Adobe', 'SAP', 'Intuit',
  'Johnson & Johnson', 'Pfizer', 'Merck', 'Abbott', 'AbbVie',
];

// Planning questions - mortgage priorities and goals
export const PLANNING_QUESTIONS = {
  mortgagePriorities: {
    question: 'What matters most to you in your mortgage?',
    hint: 'Select all that apply - this helps us find the best loan structure for you.',
    options: [
      { value: 'lowest_payment', label: 'Lowest Monthly Payment', icon: 'dollarSign' },
      { value: 'lowest_rate', label: 'Lowest Interest Rate', icon: 'trendDown' },
      { value: 'fastest_payoff', label: 'Pay Off Fastest', icon: 'bolt' },
      { value: 'lowest_total', label: 'Lowest Total Cost', icon: 'target' },
      { value: 'flexibility', label: 'Maximum Flexibility', icon: 'refresh' },
      { value: 'tax_benefits', label: 'Tax Benefits', icon: 'clipboard' },
      { value: 'build_equity', label: 'Build Equity Faster', icon: 'homeEquity' },
      { value: 'predictable', label: 'Predictable Payments', icon: 'predictable' },
    ],
  },
  personalGoals: {
    question: 'What are your personal financial goals?',
    hint: 'Select all that apply - helps us align your mortgage with your life plans.',
    options: [
      { value: 'net_worth', label: 'Building Net Worth', icon: 'netWorth' },
      { value: 'larger_home', label: 'Moving to Larger Home', icon: 'largerHome' },
      { value: 'financial_freedom', label: 'Financial Freedom', icon: 'freedom' },
      { value: 'pay_debt', label: 'Paying Off Debt', icon: 'scissors' },
      { value: 'retirement', label: 'Saving for Retirement', icon: 'retirement' },
      { value: 'education', label: 'Children\'s Education', icon: 'graduation' },
      { value: 'investments', label: 'Investment Portfolio', icon: 'barChart' },
      { value: 'business', label: 'Starting a Business', icon: 'rocket' },
    ],
  },
  financialPhilosophy: {
    question: 'How would you describe your financial approach?',
    options: [
      { value: 'conservative', label: 'Conservative', icon: 'shield', description: 'Prefer stability and lower risk' },
      { value: 'moderate', label: 'Moderate', icon: 'balance', description: 'Balance between safety and growth' },
      { value: 'aggressive', label: 'Aggressive', icon: 'rocket', description: 'Willing to take risks for higher returns' },
    ],
  },
  professionalNetwork: {
    question: 'Do you currently work with any of these professionals?',
    hint: 'We can coordinate with your existing team for a comprehensive financial plan.',
    options: [
      { value: 'financial_planner', label: 'Financial Planner', icon: 'trendUp' },
      { value: 'accountant', label: 'CPA / Accountant', icon: 'calculator' },
      { value: 'insurance_agent', label: 'Life Insurance Agent', icon: 'shield' },
      { value: 'estate_planner', label: 'Estate Planner', icon: 'fileText' },
    ],
  },
  taxDeferredRetirement: {
    question: 'Are you currently contributing to a tax-deferred retirement account?',
    hint: '401(k), IRA, or similar retirement savings',
    options: [
      { value: 'yes', label: 'Yes, I contribute regularly', icon: 'check' },
      { value: 'some', label: 'Sometimes / Not maxing out', icon: 'refresh' },
      { value: 'no', label: 'Not currently', icon: 'x' },
      { value: 'not_sure', label: 'Not sure', icon: 'helpCircle' },
    ],
  },
};
