/**
 * Shared constants for mortgage application forms (Purchase & Refinance).
 * Contains common employer list, US states, and shared planning question structures.
 */

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
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'District of Columbia' },
];

/**
 * Get API URL based on current environment.
 */
export const getApiUrl = () => {
  const isProduction = window.location.hostname !== 'localhost';
  return isProduction
    ? 'https://api.perenniaai.com'
    : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
};
