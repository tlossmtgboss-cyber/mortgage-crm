# Perennia AI - Mortgage Application Enhancement
## Complete Technical Specification

---

## Table of Contents

1. [Overview](#overview)
2. [Application Flow Routing](#application-flow-routing)
3. [Purchase Application Stages](#purchase-application-stages)
4. [Refinance Application Stages](#refinance-application-stages)
5. [Autocomplete Integrations](#autocomplete-integrations)
6. [Database Schema](#database-schema)
7. [Backend API Endpoints](#backend-api-endpoints)
8. [Document Checklist Generation](#document-checklist-generation)
9. [Frontend Components](#frontend-components)
10. [Technical Utilities](#technical-utilities)

---

## Overview

### Key Features

**Dual Application Types**
- Purchase mortgage application
- Refinance mortgage application
- Smart routing based on user selection

**Smart Autocomplete Integrations**
- Google Places API for employer information
- Google Places API for property addresses
- CRM integration for real estate agent lookup

**Intelligent Document Collection**
- Dynamic document checklist based on applicant answers
- Auto-population via document upload and AI parsing
- Mortgage statement upload with Claude Vision parsing

**Streamlined User Experience**
- Progressive disclosure (show only relevant questions)
- Auto-save functionality
- Mobile-responsive design
- Real-time validation

### Technology Stack

**Frontend:**
- React.js
- TypeScript (optional)
- CSS/Tailwind
- Google Places JavaScript API

**Backend:**
- FastAPI (Python) or Node.js
- PostgreSQL
- Anthropic Claude API (document parsing)
- Google Places API

---

## Application Flow Routing

### Entry Point: Loan Type Selection

This is the FIRST question every applicant sees.

```jsx
// pages/apply/index.js

import { useNavigate } from 'react-router-dom';

export default function ApplicationEntry() {
  const navigate = useNavigate();

  const handleLoanTypeSelection = (loanType) => {
    if (loanType === 'purchase') {
      navigate('/apply/purchase');
    } else {
      navigate('/apply/refinance');
    }
  };

  return (
    <div className="max-w-2xl mx-auto py-12">
      <h1 className="text-3xl font-bold mb-8">Let's Get Started</h1>

      <div className="mb-8">
        <label className="block text-lg font-medium mb-4">
          What type of loan are you applying for?
        </label>

        <div className="grid md:grid-cols-2 gap-4">
          <button
            onClick={() => handleLoanTypeSelection('purchase')}
            className="p-6 border-2 border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition"
          >
            <div className="text-center">
              <div className="text-4xl mb-3">🏠</div>
              <h3 className="text-xl font-semibold mb-2">Purchase</h3>
              <p className="text-gray-600">I'm buying a home</p>
            </div>
          </button>

          <button
            onClick={() => handleLoanTypeSelection('refinance')}
            className="p-6 border-2 border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition"
          >
            <div className="text-center">
              <div className="text-4xl mb-3">🔄</div>
              <h3 className="text-xl font-semibold mb-2">Refinance</h3>
              <p className="text-gray-600">I'm refinancing my current mortgage</p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Purchase Application Stages

### Stage Overview

| Stage | Name | Progress % |
|-------|------|------------|
| 1 | About You | 10% |
| 2 | New Home | 25% |
| 3 | Your Income | 40% |
| 4 | Your Assets | 55% |
| 5 | Real Estate Owned | 65% |
| 6 | Your Background | 80% |
| 7 | Government Monitoring | 85% |
| 8 | Schedule Consultation | 90% |
| 9 | Authorizations & Consent | 95% |

---

### STAGE 1: ABOUT YOU (10% Complete)

**Purpose:** Collect borrower personal information, citizenship, marital status, and residence history

#### Question 1: Veteran Status (FIRST QUESTION)

```javascript
const veteranStatusQuestion = {
  id: 'veteran_status',
  question: 'Are you a veteran or currently serving in the military?',
  type: 'single-choice',
  options: [
    { value: 'veteran', label: 'Yes - Veteran' },
    { value: 'active_duty', label: 'Yes - Active Duty' },
    { value: 'reserves', label: 'Yes - Reserves/National Guard' },
    { value: 'no', label: 'No' }
  ],
  required: true
};

// Conditional Follow-ups (if veteran/active duty/reserves):
const vaFollowUpQuestions = [
  {
    id: 'va_loan_history',
    question: 'Have you used a VA loan before?',
    type: 'single-choice',
    options: [
      { value: 'paid_off', label: 'Yes - Paid off' },
      { value: 'still_have', label: 'Yes - Still have it' },
      { value: 'first_time', label: 'No - First VA loan' }
    ],
    showIf: { veteran_status: ['veteran', 'active_duty', 'reserves'] }
  },
  {
    id: 'va_disability',
    question: 'Do you have a VA disability rating?',
    type: 'single-choice',
    options: [
      { value: 'yes_10_plus', label: 'Yes - 10% or higher' },
      { value: 'pending', label: 'Pending' },
      { value: 'no', label: 'No' }
    ],
    showIf: { veteran_status: ['veteran', 'active_duty', 'reserves'] }
  }
];
```

#### Question 2: Borrower Count

```javascript
const borrowerCountQuestion = {
  id: 'borrower_count',
  question: 'How many people will be on this loan application?',
  type: 'single-choice',
  options: [
    { value: '1', label: '1' },
    { value: '2', label: '2' },
    { value: '3', label: '3' },
    { value: '4+', label: '4+' }
  ],
  required: true
};

// Conditional (if 2+):
const borrowerRelationshipQuestion = {
  id: 'borrower_relationship',
  question: 'What is your relationship to the other borrower(s)?',
  type: 'single-choice',
  options: [
    { value: 'spouse', label: 'Spouse/Partner' },
    { value: 'family', label: 'Family member' },
    { value: 'friend', label: 'Friend' },
    { value: 'business', label: 'Business partner' }
  ],
  showIf: { borrower_count: ['2', '3', '4+'] }
};
```

#### Questions 3-8: Primary Borrower Information

```javascript
const borrowerFields = [
  {
    id: 'first_name',
    label: 'First Name',
    type: 'text',
    required: true,
    validation: { minLength: 1, maxLength: 50 }
  },
  {
    id: 'last_name',
    label: 'Last Name',
    type: 'text',
    required: true,
    validation: { minLength: 1, maxLength: 50 }
  },
  {
    id: 'email',
    label: 'Email',
    type: 'email',
    required: true,
    validation: { pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/ }
  },
  {
    id: 'phone',
    label: 'Phone',
    type: 'tel',
    required: true,
    validation: { pattern: /^\d{10}$/ },
    format: 'phone' // Auto-format as (XXX) XXX-XXXX
  },
  {
    id: 'date_of_birth',
    label: 'Date of Birth',
    type: 'date',
    required: true,
    validation: { minAge: 18 }
  },
  {
    id: 'ssn',
    label: 'Social Security Number',
    type: 'ssn',
    required: true,
    masked: true, // Display as XXX-XX-1234
    validation: { pattern: /^\d{9}$/ }
  }
];
```

#### Question 9: Citizenship

```javascript
const citizenshipQuestion = {
  id: 'citizenship_status',
  question: 'What is your citizenship status?',
  type: 'single-choice',
  options: [
    { value: 'us_citizen', label: 'U.S. Citizen' },
    { value: 'permanent_resident', label: 'Permanent Resident' },
    { value: 'non_permanent_resident', label: 'Non-Permanent Resident' },
    { value: 'non_resident_alien', label: 'Non-Resident Alien' }
  ],
  required: true
};
```

#### Question 10: Marital Status

```javascript
const maritalStatusQuestion = {
  id: 'marital_status',
  question: 'Are you married?',
  type: 'single-choice',
  options: [
    { value: 'married', label: 'Married' },
    { value: 'single', label: 'Single' },
    { value: 'divorced', label: 'Divorced' },
    { value: 'separated', label: 'Separated' },
    { value: 'widowed', label: 'Widowed' }
  ],
  required: true
};

// Conditional (if married):
const spouseFields = [
  {
    id: 'spouse_first_name',
    label: "Spouse's First Name",
    type: 'text',
    showIf: { marital_status: 'married' }
  },
  {
    id: 'spouse_last_name',
    label: "Spouse's Last Name",
    type: 'text',
    showIf: { marital_status: 'married' }
  },
  {
    id: 'spouse_on_loan',
    question: 'Will your spouse be on the loan application?',
    type: 'boolean',
    showIf: { marital_status: 'married' }
  }
];

// Conditional (if divorced/separated):
const divorceQuestion = {
  id: 'divorce_finalized',
  question: 'Is your divorce finalized?',
  type: 'single-choice',
  options: [
    { value: 'yes', label: 'Yes' },
    { value: 'pending', label: 'Pending' }
  ],
  showIf: { marital_status: ['divorced', 'separated'] }
};
```

#### Questions 11-15: Current Residence

```javascript
const currentResidenceFields = [
  {
    id: 'current_street',
    label: 'Street Address',
    type: 'text',
    required: true,
    autocomplete: 'google-places' // Uses Google Places Autocomplete
  },
  {
    id: 'current_city',
    label: 'City',
    type: 'text',
    required: true,
    autoFilled: true // Filled by autocomplete
  },
  {
    id: 'current_state',
    label: 'State',
    type: 'select',
    required: true,
    autoFilled: true
  },
  {
    id: 'current_zip',
    label: 'ZIP Code',
    type: 'text',
    required: true,
    validation: { pattern: /^\d{5}(-\d{4})?$/ },
    autoFilled: true
  },
  {
    id: 'time_at_address_years',
    label: 'How long at this address? (Years)',
    type: 'number',
    required: true,
    min: 0,
    max: 99
  },
  {
    id: 'time_at_address_months',
    label: 'Months',
    type: 'number',
    required: true,
    min: 0,
    max: 11
  },
  {
    id: 'housing_status',
    question: 'Housing Status',
    type: 'single-choice',
    options: [
      { value: 'own', label: 'Own' },
      { value: 'rent', label: 'Rent' },
      { value: 'living_rent_free', label: 'Living Rent Free' }
    ],
    required: true
  },
  {
    id: 'monthly_housing_payment',
    label: 'Monthly housing payment (rent or mortgage)',
    type: 'currency',
    required: true,
    showIf: { housing_status: ['own', 'rent'] }
  }
];
```

#### Questions 16-20: Previous Residence (if < 2 years at current)

```javascript
// Show only if time_at_address_years + (time_at_address_months / 12) < 2

const previousResidenceFields = [
  {
    id: 'previous_street',
    label: 'Previous Street Address',
    type: 'text',
    required: true,
    showIf: (data) => calculateYearsAtAddress(data) < 2
  },
  {
    id: 'previous_city',
    label: 'City',
    type: 'text',
    required: true
  },
  {
    id: 'previous_state',
    label: 'State',
    type: 'select',
    required: true
  },
  {
    id: 'previous_zip',
    label: 'ZIP Code',
    type: 'text',
    required: true
  },
  {
    id: 'previous_time_years',
    label: 'How long at this address? (Years)',
    type: 'number',
    required: true
  },
  {
    id: 'previous_time_months',
    label: 'Months',
    type: 'number',
    required: true
  },
  {
    id: 'previous_housing_status',
    question: 'Housing Status',
    type: 'single-choice',
    options: [
      { value: 'own', label: 'Own' },
      { value: 'rent', label: 'Rent' },
      { value: 'living_rent_free', label: 'Living Rent Free' }
    ],
    required: true
  }
];

// Validation: Total residence history must equal 2 years
function validateResidenceHistory(data) {
  const currentYears = data.time_at_address_years + (data.time_at_address_months / 12);
  const previousYears = (data.previous_time_years || 0) + ((data.previous_time_months || 0) / 12);
  return currentYears + previousYears >= 2;
}
```

#### Co-Borrower Information

```javascript
// If borrower_count > 1, repeat ALL Stage 1 questions for each additional borrower
// Store as array: borrowers[0] = primary, borrowers[1] = co-borrower 1, etc.

const borrowerDataStructure = {
  borrowers: [
    {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      date_of_birth: '',
      ssn: '',
      citizenship_status: '',
      marital_status: '',
      spouse_first_name: '',
      spouse_last_name: '',
      current_residence: {
        street: '',
        city: '',
        state: '',
        zip: '',
        years: 0,
        months: 0,
        housing_status: '',
        monthly_payment: 0
      },
      previous_residence: null, // Only if < 2 years at current
      residence_history_complete: false
    }
  ]
};
```

---

### STAGE 2: NEW HOME (25% Complete)

**Purpose:** Collect property details, location, type, budget, and real estate agent info

#### Questions 1-2: Property Location

```javascript
const propertyLocationQuestions = [
  {
    id: 'property_state',
    question: 'What state are you looking to buy in?',
    type: 'select',
    options: US_STATES, // Array of all US states
    required: true
  },
  {
    id: 'property_city_area',
    question: 'What city or area are you looking to buy in?',
    type: 'text',
    required: true,
    placeholder: 'e.g., Charleston, Mount Pleasant, etc.'
  }
];
```

#### Questions 3-4: Property Search Status

```javascript
const propertySearchQuestions = [
  {
    id: 'property_search_status',
    question: 'Have you found a property yet?',
    type: 'single-choice',
    options: [
      { value: 'under_contract', label: 'Under contract' },
      { value: 'still_shopping', label: 'Still shopping' },
      { value: 'pre_approval', label: 'Just getting pre-approved' }
    ],
    required: true
  },
  {
    id: 'closing_date',
    question: 'When is your target closing date?',
    type: 'single-choice',
    options: [
      { value: '<30', label: 'Less than 30 days' },
      { value: '30-45', label: '30-45 days' },
      { value: '45-60', label: '45-60 days' },
      { value: '60+', label: '60+ days' }
    ],
    showIf: { property_search_status: 'under_contract' }
  }
];
```

#### Questions 5-9: Real Estate Agent

```javascript
const realtorQuestions = [
  {
    id: 'has_realtor',
    question: 'Are you working with a real estate agent?',
    type: 'boolean',
    required: true
  }
];

// If Yes - Use CRM Autocomplete Component:
const realtorFields = [
  {
    id: 'realtor_name',
    label: 'Agent Name',
    type: 'text',
    autocomplete: 'crm', // Special autocomplete type - searches CRM
    required: true,
    showIf: { has_realtor: true }
  },
  {
    id: 'realtor_phone',
    label: 'Agent Phone',
    type: 'tel',
    autoFilled: true // From CRM selection
  },
  {
    id: 'realtor_email',
    label: 'Agent Email',
    type: 'email',
    autoFilled: true
  },
  {
    id: 'realtor_company',
    label: 'Agent Company',
    type: 'text',
    autoFilled: true
  }
];
```

#### Question 10: Property Type

```javascript
const propertyTypeQuestion = {
  id: 'property_type',
  question: 'What type of property are you purchasing?',
  type: 'single-choice',
  options: [
    { value: 'single_family', label: 'Single Family' },
    { value: 'condo', label: 'Condo' },
    { value: 'townhouse', label: 'Townhouse' },
    { value: 'multi_family', label: 'Multi-Family' }
  ],
  required: true
};

// Conditional (if multi_family):
const unitsQuestion = {
  id: 'number_of_units',
  question: 'How many units does this property have?',
  type: 'single-choice',
  options: [
    { value: '2', label: '2 units' },
    { value: '3', label: '3 units' },
    { value: '4', label: '4 units' }
  ],
  showIf: { property_type: 'multi_family' },
  required: true
};
```

#### Question 11: Occupancy

```javascript
const occupancyQuestion = {
  id: 'occupancy_type',
  question: 'How will you use this property?',
  type: 'single-choice',
  options: [
    { value: 'primary', label: 'Primary Home' },
    { value: 'second_home', label: 'Second Home' },
    { value: 'investment', label: 'Investment' }
  ],
  required: true
};
```

#### Question 12: First-Time Buyer

```javascript
const firstTimeBuyerQuestion = {
  id: 'first_time_buyer',
  question: 'Is this your first home purchase?',
  type: 'boolean',
  required: true
};
```

#### Questions 13-17: Property Address (if known)

```javascript
const propertyAddressQuestions = [
  {
    id: 'property_address_known',
    question: 'Have you identified the specific property address?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'no', label: 'No' },
      { value: 'shopping', label: 'Still shopping' }
    ],
    required: true
  }
];

// If Yes - Use Google Places Autocomplete:
const propertyAddressFields = [
  {
    id: 'property_street',
    label: 'Street Address',
    type: 'text',
    autocomplete: 'google-places',
    showIf: { property_address_known: 'yes' }
  },
  {
    id: 'property_city',
    label: 'City',
    type: 'text',
    autoFilled: true
  },
  {
    id: 'property_state',
    label: 'State',
    type: 'select',
    autoFilled: true
  },
  {
    id: 'property_zip',
    label: 'ZIP Code',
    type: 'text',
    autoFilled: true
  },
  {
    id: 'mls_number',
    label: 'MLS Number (Optional)',
    type: 'text',
    optional: true
  }
];
```

#### Questions 18-19: Budget

```javascript
const budgetFields = [
  {
    id: 'purchase_price',
    label: 'Purchase Price',
    type: 'currency',
    required: true,
    validation: { min: 50000, max: 10000000 }
  },
  {
    id: 'down_payment',
    label: 'Down Payment Amount',
    type: 'currency',
    required: true,
    validation: {
      min: (data) => data.purchase_price * 0.03, // Minimum 3%
      max: (data) => data.purchase_price * 0.99
    }
  },
  {
    id: 'down_payment_percentage',
    label: 'Down Payment %',
    type: 'percentage',
    calculated: true, // Auto-calculated: (down_payment / purchase_price) * 100
    display: 'readonly'
  }
];
```

#### Questions 20-21: HOA (if Condo/Townhouse)

```javascript
const hoaFields = [
  {
    id: 'monthly_hoa_fee',
    question: 'What is the monthly HOA or condo fee?',
    type: 'currency',
    showIf: { property_type: ['condo', 'townhouse'] },
    allowUnknown: true // Checkbox: "Don't know yet"
  },
  {
    id: 'hoa_name',
    label: "What is the name of the HOA or condo association? (Optional)",
    type: 'text',
    optional: true,
    showIf: { property_type: ['condo', 'townhouse'] }
  }
];
```

#### Questions 22-23: Estimated Costs

```javascript
const estimatedCostsFields = [
  {
    id: 'estimated_annual_property_tax',
    label: 'Estimated annual property taxes',
    type: 'currency',
    allowUnknown: true,
    helpText: "We can help estimate this if you don't know"
  },
  {
    id: 'estimated_annual_insurance',
    label: 'Estimated annual homeowners insurance',
    type: 'currency',
    allowUnknown: true,
    helpText: "We can help estimate this if you don't know"
  }
];
```

#### Question 24: Seller Relationship

```javascript
const sellerRelationshipQuestion = {
  id: 'seller_relationship',
  question: 'Do you have a family relationship or business affiliation with the seller?',
  type: 'single-choice',
  options: [
    { value: 'family', label: 'Yes - Family' },
    { value: 'business', label: 'Yes - Business' },
    { value: 'no', label: 'No' }
  ],
  required: true
};

// Conditional (if yes):
const sellerRelationshipDescription = {
  id: 'seller_relationship_description',
  label: 'Describe relationship',
  type: 'textarea',
  showIf: { seller_relationship: ['family', 'business'] },
  required: true,
  maxLength: 500
};
```

---

### STAGE 3: YOUR INCOME (40% Complete)

**Purpose:** Collect employment history, income sources, and verify 2 years of employment

#### Question 1: Employment Status

```javascript
const employmentStatusQuestion = {
  id: 'employment_status',
  question: 'Are you self-employed or own a business?',
  type: 'single-choice',
  options: [
    { value: 'self_employed', label: 'Yes' },
    { value: 'side_business', label: 'Side business' },
    { value: 'w2_employee', label: 'W-2 employee' }
  ],
  required: true
};
```

#### W-2 EMPLOYEE PATH - Questions 2-7: Current Employer

```javascript
const w2CurrentEmployerFields = [
  {
    id: 'employer_name',
    label: 'Employer Name',
    type: 'text',
    autocomplete: 'google-places-business', // Uses Google Places API
    required: true
  },
  {
    id: 'employer_address',
    label: 'Employer Address',
    type: 'text',
    autoFilled: true, // Filled by Google Places
    display: 'readonly'
  },
  {
    id: 'employer_phone',
    label: 'Employer Phone',
    type: 'tel',
    autoFilled: true
  },
  {
    id: 'job_title',
    label: 'Job Title',
    type: 'text',
    required: true
  },
  {
    id: 'employment_start_date',
    label: 'Employment Start Date',
    type: 'month-year',
    required: true,
    validation: { maxDate: 'today' }
  },
  {
    id: 'annual_base_salary',
    label: 'Annual Base Salary',
    type: 'currency',
    required: true,
    validation: { min: 0, max: 10000000 }
  }
];
```

#### W-2 EMPLOYEE PATH - Questions 8-13: Previous Employer (if < 2 years)

```javascript
// Show if employment_start_date is less than 2 years ago

const w2PreviousEmployerFields = [
  {
    id: 'previous_employer_name',
    label: 'Previous Employer Name',
    type: 'text',
    required: true,
    showIf: (data) => calculateEmploymentDuration(data.employment_start_date) < 2
  },
  {
    id: 'previous_job_title',
    label: 'Job Title',
    type: 'text',
    required: true
  },
  {
    id: 'previous_start_date',
    label: 'Start Date',
    type: 'month-year',
    required: true
  },
  {
    id: 'previous_end_date',
    label: 'End Date',
    type: 'month-year',
    required: true,
    validation: {
      afterStart: true,
      beforeCurrent: (data) => data.employment_start_date
    }
  },
  {
    id: 'previous_annual_salary',
    label: 'Annual Salary',
    type: 'currency',
    required: true
  }
];

// Validation: Total employment must be >= 2 years
function validateEmploymentHistory(data) {
  const currentDuration = calculateEmploymentDuration(data.employment_start_date);
  if (currentDuration >= 2) return true;

  const previousDuration = calculateMonthsBetween(
    data.previous_start_date,
    data.previous_end_date
  ) / 12;

  return currentDuration + previousDuration >= 2;
}
```

#### W-2 EMPLOYEE PATH - Questions 14-18: Second Job

```javascript
const secondJobQuestion = {
  id: 'has_second_job',
  question: 'Do you have a second job?',
  type: 'boolean'
};

// If Yes:
const secondJobFields = [
  {
    id: 'second_job_employer',
    label: 'Employer Name',
    type: 'text',
    showIf: { has_second_job: true }
  },
  {
    id: 'second_job_title',
    label: 'Job Title',
    type: 'text'
  },
  {
    id: 'second_job_start_date',
    label: 'Start Date',
    type: 'month-year'
  },
  {
    id: 'second_job_annual_income',
    label: 'Annual Income',
    type: 'currency'
  }
];
```

#### SELF-EMPLOYED PATH - Questions 2-6

```javascript
const selfEmployedQuestions = [
  {
    id: 'self_employment_duration',
    question: 'How long have you been self-employed?',
    type: 'single-choice',
    options: [
      { value: '<1', label: 'Less than 1 year' },
      { value: '1-2', label: '1-2 years' },
      { value: '2+', label: '2+ years' }
    ],
    showIf: { employment_status: ['self_employed', 'side_business'] }
  },
  {
    id: 'business_structure',
    question: 'What type of business do you have?',
    type: 'single-choice',
    options: [
      { value: 'sole_proprietor', label: 'Sole proprietor' },
      { value: 'llc', label: 'LLC' },
      { value: 's_corp', label: 'S-Corp' },
      { value: 'c_corp', label: 'C-Corp' },
      { value: 'partnership', label: 'Partnership' }
    ]
  },
  {
    id: 'filed_tax_returns',
    question: 'Have you filed your prior year tax returns?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'no', label: 'No' },
      { value: 'extension', label: 'Extension' }
    ]
  },
  {
    id: 'write_off_expenses',
    question: 'Do you write off most expenses to minimize taxable income?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'some', label: 'Some' },
      { value: 'no', label: 'No' }
    ]
  }
];
```

#### SELF-EMPLOYED PATH - Questions 7-11: Business Information

```javascript
const businessInfoFields = [
  {
    id: 'business_name',
    label: 'Business Name',
    type: 'text',
    required: true
  },
  {
    id: 'business_type',
    label: 'Business Type',
    type: 'select',
    options: [
      { value: 'sole_proprietor', label: 'Sole Proprietor' },
      { value: 'llc', label: 'LLC' },
      { value: 's_corp', label: 'S-Corp' },
      { value: 'c_corp', label: 'C-Corp' },
      { value: 'partnership', label: 'Partnership' }
    ],
    required: true
  },
  {
    id: 'ownership_percentage',
    label: 'Ownership Percentage',
    type: 'percentage',
    required: true,
    validation: { min: 1, max: 100 }
  },
  {
    id: 'annual_net_income',
    label: 'Annual Net Income (from tax returns)',
    type: 'currency',
    required: true,
    helpText: 'This is your net income after business expenses'
  }
];
```

#### Additional Income (All Employment Types)

```javascript
const additionalIncomeQuestion = {
  id: 'has_additional_income',
  question: 'Do you have any additional income?',
  type: 'boolean'
};

// If Yes:
const additionalIncomeFields = [
  {
    id: 'monthly_rental_income',
    label: 'Monthly Rental Income',
    type: 'currency',
    optional: true,
    showIf: { has_additional_income: true }
  },
  {
    id: 'other_monthly_income',
    label: 'Other Monthly Income',
    type: 'currency',
    optional: true
  },
  {
    id: 'other_income_source',
    label: 'Source of other income',
    type: 'text',
    placeholder: 'e.g., Social Security, Pension, Investments',
    showIf: (data) => data.other_monthly_income > 0
  }
];
```

#### Child Support & Alimony Income

```javascript
const alimonyIncomeQuestion = {
  id: 'receives_alimony_child_support',
  question: 'Do you receive child support or alimony?',
  type: 'boolean'
};

// If Yes:
const alimonyIncomeFields = [
  {
    id: 'monthly_alimony_child_support_received',
    label: 'How much do you receive per month?',
    type: 'currency',
    showIf: { receives_alimony_child_support: true }
  },
  {
    id: 'alimony_child_support_duration',
    question: 'How long have you been receiving this income?',
    type: 'single-choice',
    options: [
      { value: '<6mo', label: 'Less than 6 months' },
      { value: '6-12mo', label: '6-12 months' },
      { value: '1-2yr', label: '1-2 years' },
      { value: '2+yr', label: '2+ years' }
    ]
  },
  {
    id: 'alimony_child_support_type_received',
    question: 'What type of payments?',
    type: 'single-choice',
    options: [
      { value: 'child_support', label: 'Child Support' },
      { value: 'alimony', label: 'Alimony' },
      { value: 'both', label: 'Both' }
    ]
  }
];
```

---

### STAGE 4: YOUR ASSETS (55% Complete)

**Purpose:** Collect asset information for down payment and reserves

#### Questions 1-4: Liquid Assets

```javascript
const assetFields = [
  {
    id: 'checking_total',
    label: 'Checking Accounts (total balance)',
    type: 'currency',
    required: true,
    validation: { min: 0 }
  },
  {
    id: 'savings_total',
    label: 'Savings Accounts (total balance)',
    type: 'currency',
    required: true,
    validation: { min: 0 }
  },
  {
    id: 'investments_total',
    label: 'Investment Accounts (stocks, bonds, mutual funds)',
    type: 'currency',
    required: true,
    validation: { min: 0 }
  },
  {
    id: 'retirement_total',
    label: 'Retirement Accounts (401k, IRA, etc.)',
    type: 'currency',
    required: true,
    validation: { min: 0 },
    helpText: 'Note: Retirement funds typically cannot be used for down payment unless withdrawn'
  }
];
```

#### Questions 5-8: Gift Funds

```javascript
const giftFundsQuestion = {
  id: 'using_gift_funds',
  question: 'Will you use gift funds for your down payment or closing costs?',
  type: 'single-choice',
  options: [
    { value: 'yes', label: 'Yes' },
    { value: 'maybe', label: 'Maybe' },
    { value: 'no', label: 'No' }
  ],
  required: true
};

// If Yes or Maybe:
const giftFundsFields = [
  {
    id: 'gift_amount',
    label: 'How much gift money will you receive?',
    type: 'currency',
    showIf: { using_gift_funds: ['yes', 'maybe'] },
    validation: {
      max: (data) => data.down_payment + 10000 // Down payment + estimated closing
    }
  },
  {
    id: 'gift_donor_relationship',
    question: 'Who is providing the gift?',
    type: 'single-choice',
    options: [
      { value: 'parent', label: 'Parent' },
      { value: 'grandparent', label: 'Grandparent' },
      { value: 'sibling', label: 'Sibling' },
      { value: 'other_relative', label: 'Other relative' },
      { value: 'non_relative', label: 'Non-relative' }
    ]
  },
  {
    id: 'gift_donor_name',
    label: 'Gift Donor Name',
    type: 'text'
  }
];
```

---

### STAGE 5: REAL ESTATE OWNED (65% Complete)

**Purpose:** Collect information about other properties owned

#### Question 1: Ownership Check

```javascript
const ownsPropertyQuestion = {
  id: 'owns_other_property',
  question: 'Do you own any other real estate property?',
  type: 'boolean',
  required: true
};
// If No: Skip to Stage 6
// If Yes: Continue to property collection loop
```

#### For Each Property: Question 2 - Mortgage Status

```javascript
const propertyMortgageQuestion = (index) => ({
  id: `property_${index}_has_mortgage`,
  question: `Property #${index + 1}: Do you have a mortgage on this property?`,
  type: 'boolean',
  required: true
});
```

#### If Has Mortgage: Question 3 - Statement Upload Option

```javascript
const statementUploadQuestion = (index) => ({
  id: `property_${index}_can_upload_statement`,
  question: 'Can you upload your most recent mortgage statement?',
  type: 'single-choice',
  options: [
    { value: 'yes', label: "Yes, I have it" },
    { value: 'no', label: "No, I'll enter manually" }
  ],
  helpText: "This is the fastest way - we'll extract all the details automatically"
});
```

#### If Yes → Upload Flow with Claude Vision Parsing

```javascript
// Component: MortgageStatementUpload
const mortgageStatementUpload = {
  type: 'file-upload',
  acceptedTypes: ['application/pdf', 'image/jpeg', 'image/png'],
  maxSize: 10485760, // 10MB

  onUpload: async (file) => {
    // 1. Upload file to storage
    const filePath = await uploadFile(file, `reo-statements/${applicationId}`);

    // 2. Parse with Claude Vision API
    const parsedData = await parseStatementWithClaude(file);

    // 3. Return parsed data for review
    return {
      status: 'success',
      data: parsedData,
      filePath: filePath,
      confidence: parsedData.confidence
    };
  }
};

// Parsed data structure returned from Claude:
const parsedMortgageStatementStructure = {
  property_address: {
    street: '',
    city: '',
    state: '',
    zip: ''
  },
  lender_name: '',
  loan_number: '',
  current_balance: 0,
  monthly_pi_payment: 0,
  monthly_property_tax: 0,
  monthly_insurance: 0,
  monthly_hoa: 0,
  interest_rate: 0,
  total_monthly_payment: 0, // Calculated
  confidence: {
    overall: 0, // 0-100
    property_address: 0,
    payment_amounts: 0,
    loan_balance: 0
  }
};
```

#### Manual Entry: Free & Clear Form (No Mortgage)

```javascript
const freeAndClearFields = (index) => [
  {
    id: `property_${index}_street`,
    label: 'Street Address',
    type: 'text',
    autocomplete: 'google-places-address',
    required: true
  },
  {
    id: `property_${index}_city`,
    label: 'City',
    type: 'text',
    autoFilled: true
  },
  {
    id: `property_${index}_state`,
    label: 'State',
    type: 'select',
    autoFilled: true
  },
  {
    id: `property_${index}_zip`,
    label: 'ZIP Code',
    type: 'text',
    autoFilled: true
  },
  {
    id: `property_${index}_type`,
    question: 'Property Type',
    type: 'single-choice',
    options: [
      { value: 'single_family', label: 'Single Family' },
      { value: 'condo', label: 'Condo' },
      { value: 'townhouse', label: 'Townhouse' },
      { value: 'multi_family', label: 'Multi-family' }
    ]
  },
  {
    id: `property_${index}_use`,
    question: 'Current Use',
    type: 'single-choice',
    options: [
      { value: 'primary', label: 'Primary Residence' },
      { value: 'rental', label: 'Rental' },
      { value: 'vacant', label: 'Vacant' },
      { value: 'second_home', label: 'Second Home' }
    ]
  },
  {
    id: `property_${index}_value`,
    label: 'Current Market Value',
    type: 'currency',
    required: true
  },
  {
    id: `property_${index}_monthly_tax`,
    label: 'Monthly Property Taxes',
    type: 'currency'
  },
  {
    id: `property_${index}_monthly_insurance`,
    label: 'Monthly Homeowners Insurance',
    type: 'currency'
  },
  {
    id: `property_${index}_monthly_hoa`,
    label: 'Monthly HOA Fees (if applicable)',
    type: 'currency',
    optional: true
  }
];

// If Rental:
const rentalFields = (index) => [
  {
    id: `property_${index}_monthly_rental_income`,
    label: 'Monthly Rental Income',
    type: 'currency',
    showIf: { [`property_${index}_use`]: 'rental' }
  },
  {
    id: `property_${index}_has_lease`,
    question: 'Do you have a lease in place?',
    type: 'boolean',
    showIf: { [`property_${index}_use`]: 'rental' }
  }
];
```

#### Manual Entry: With Mortgage Form

```javascript
// If property_${index}_has_mortgage === true AND can_upload_statement === 'no'

const withMortgageFields = (index) => [
  // All Free & Clear fields PLUS:
  {
    id: `property_${index}_lender_name`,
    label: 'Lender/Servicer Name',
    type: 'text',
    required: true
  },
  {
    id: `property_${index}_loan_number`,
    label: 'Loan Number (Optional)',
    type: 'text',
    optional: true
  },
  {
    id: `property_${index}_loan_balance`,
    label: 'Current Loan Balance',
    type: 'currency',
    required: true
  },
  {
    id: `property_${index}_monthly_pi`,
    label: 'Monthly Principal & Interest Payment',
    type: 'currency',
    required: true
  },
  {
    id: `property_${index}_interest_rate`,
    label: 'Interest Rate (Optional)',
    type: 'percentage',
    optional: true
  }
];
```

#### Question: Add Another Property

```javascript
const addAnotherPropertyQuestion = {
  id: 'add_another_property',
  question: 'Do you have another property to add?',
  type: 'boolean'
};
// If Yes: Loop back to Question 2 for next property
// If No: Continue to Stage 6
```

---

### STAGE 6: YOUR BACKGROUND (80% Complete)

**Purpose:** Collect declarations, credit history, and legal disclosures

#### Previous Home History (if NOT first-time buyer)

```javascript
const previousHomeQuestions = [
  {
    id: 'previous_home_status',
    question: 'What happened to your previous home?',
    type: 'single-choice',
    options: [
      { value: 'sold', label: 'Sold' },
      { value: 'second_home', label: 'Keeping as second home' },
      { value: 'renting_out', label: 'Renting out' },
      { value: 'foreclosure', label: 'Foreclosure' }
    ],
    showIf: { first_time_buyer: false }
  },
  // If foreclosure:
  {
    id: 'foreclosure_date',
    question: 'When did the foreclosure occur?',
    type: 'single-choice',
    options: [
      { value: '<1yr', label: 'Less than 1 year ago' },
      { value: '1-2yr', label: '1-2 years ago' },
      { value: '2-3yr', label: '2-3 years ago' },
      { value: '3-5yr', label: '3-5 years ago' },
      { value: '5-7yr', label: '5-7 years ago' }
    ],
    showIf: { previous_home_status: 'foreclosure' }
  }
];
```

#### Deed in Lieu of Foreclosure

```javascript
const deedInLieuQuestions = [
  {
    id: 'deed_in_lieu',
    question: 'In the past 7 years, have you conveyed title to a property in lieu of foreclosure?',
    type: 'boolean'
  },
  {
    id: 'deed_in_lieu_date',
    question: 'When did this occur?',
    type: 'single-choice',
    options: [
      { value: '1-2yr', label: '1-2 years ago' },
      { value: '2-3yr', label: '2-3 years ago' },
      { value: '3-5yr', label: '3-5 years ago' },
      { value: '5-7yr', label: '5-7 years ago' }
    ],
    showIf: { deed_in_lieu: true }
  }
];
```

#### Monthly Obligations - Child Support & Alimony Payments

```javascript
const alimonyPaymentQuestions = [
  {
    id: 'pays_alimony_child_support',
    question: 'Do you pay child support or alimony?',
    type: 'boolean'
  },
  {
    id: 'monthly_alimony_child_support_paid',
    label: 'How much do you pay per month?',
    type: 'currency',
    showIf: { pays_alimony_child_support: true }
  },
  {
    id: 'alimony_child_support_type_paid',
    question: 'What type of payments?',
    type: 'single-choice',
    options: [
      { value: 'child_support', label: 'Child Support' },
      { value: 'alimony', label: 'Alimony' },
      { value: 'both', label: 'Both' }
    ],
    showIf: { pays_alimony_child_support: true }
  },
  {
    id: 'alimony_child_support_duration_remaining',
    question: 'How long will you continue making payments?',
    type: 'single-choice',
    options: [
      { value: '<1yr', label: 'Less than 1 year' },
      { value: '1-3yr', label: '1-3 years' },
      { value: '3-5yr', label: '3-5 years' },
      { value: '5-10yr', label: '5-10 years' },
      { value: '10+yr', label: '10+ years' }
    ],
    showIf: { pays_alimony_child_support: true }
  }
];
```

#### Child Care Expenses

```javascript
const childcareQuestions = [
  {
    id: 'has_childcare_expenses',
    question: "Do you have monthly child care expenses that you're obligated to pay?",
    type: 'boolean'
  },
  {
    id: 'monthly_childcare_expense',
    label: 'Monthly amount',
    type: 'currency',
    showIf: { has_childcare_expenses: true }
  }
];
```

#### Tax & Debt Issues - IRS Debt

```javascript
const irsDebtQuestions = [
  {
    id: 'irs_debt',
    question: 'Do you have an outstanding balance owed to the IRS?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'payment_plan', label: 'Payment plan' },
      { value: 'no', label: 'No' }
    ]
  },
  {
    id: 'irs_monthly_payment',
    label: "What's the monthly payment?",
    type: 'currency',
    showIf: { irs_debt: ['yes', 'payment_plan'] }
  },
  {
    id: 'irs_payment_current',
    question: 'Are you current on your IRS payment plan?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'behind', label: 'Behind' }
    ],
    showIf: { irs_debt: 'payment_plan' }
  }
];
```

#### Federal Debt

```javascript
const federalDebtQuestions = [
  {
    id: 'federal_debt_delinquent',
    question: 'Are you presently delinquent or in default on any federal debt?',
    type: 'boolean',
    helpText: 'Student loans, SBA loans, tax liens, etc.'
  },
  {
    id: 'federal_debt_type',
    question: 'Type of debt',
    type: 'single-choice',
    options: [
      { value: 'student_loan', label: 'Federal Student Loan' },
      { value: 'sba_loan', label: 'SBA Loan' },
      { value: 'tax_lien', label: 'Tax Lien' },
      { value: 'other', label: 'Other Federal Debt' }
    ],
    showIf: { federal_debt_delinquent: true }
  }
];
```

#### Credit History - Recent Applications

```javascript
const recentCreditQuestions = [
  {
    id: 'recent_credit_applications',
    question: 'Have you applied for any credit in the past 3 months?',
    type: 'boolean'
  },
  {
    id: 'credit_application_type',
    question: 'What type of credit?',
    type: 'single-choice',
    options: [
      { value: 'auto', label: 'Auto loan' },
      { value: 'credit_card', label: 'Credit card' },
      { value: 'personal', label: 'Personal loan' },
      { value: 'other', label: 'Other' }
    ],
    showIf: { recent_credit_applications: true }
  },
  {
    id: 'credit_application_status',
    question: 'Was the credit application approved?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'pending', label: 'Pending' },
      { value: 'no', label: 'No' }
    ],
    showIf: { recent_credit_applications: true }
  }
];
```

#### Credit Challenges & Bankruptcy

```javascript
const creditChallengesQuestions = [
  {
    id: 'credit_challenges',
    question: 'Have you had any credit challenges in the past 2 years?',
    type: 'single-choice',
    options: [
      { value: 'none', label: 'None' },
      { value: 'late_payments', label: 'Late payments' },
      { value: 'collections', label: 'Collections' },
      { value: 'bankruptcy', label: 'Bankruptcy' }
    ]
  },
  {
    id: 'bankruptcy_type',
    question: 'What type of bankruptcy?',
    type: 'single-choice',
    options: [
      { value: 'chapter_7', label: 'Chapter 7' },
      { value: 'chapter_13', label: 'Chapter 13' },
      { value: 'chapter_12', label: 'Chapter 12' }
    ],
    showIf: { credit_challenges: 'bankruptcy' }
  },
  {
    id: 'bankruptcy_discharge_date',
    question: 'When was it discharged?',
    type: 'single-choice',
    options: [
      { value: '<1yr', label: 'Less than 1 year ago' },
      { value: '1-2yr', label: '1-2 years ago' },
      { value: '2-3yr', label: '2-3 years ago' },
      { value: '3-5yr', label: '3-5 years ago' },
      { value: '5-7yr', label: '5-7 years ago' }
    ],
    showIf: { credit_challenges: 'bankruptcy' }
  },
  {
    id: 'chapter_13_status',
    question: 'Chapter 13 status',
    type: 'single-choice',
    options: [
      { value: 'paying', label: 'Actively paying' },
      { value: 'completed', label: 'Completed' }
    ],
    showIf: { bankruptcy_type: 'chapter_13' }
  }
];
```

#### Legal Issues

```javascript
const legalIssuesQuestions = [
  {
    id: 'lawsuit_or_judgment',
    question: 'Are you currently a party to a lawsuit or have outstanding judgments?',
    type: 'boolean'
  },
  {
    id: 'lawsuit_description',
    label: 'Brief description',
    type: 'textarea',
    maxLength: 500,
    showIf: { lawsuit_or_judgment: true }
  }
];
```

#### Transaction-Specific Declarations

```javascript
const transactionDeclarations = [
  {
    id: 'undisclosed_borrowed_funds',
    question: 'Will you borrow any money for this transaction that you have not disclosed?',
    type: 'boolean',
    helpText: 'Such as money for closing costs or down payment'
  },
  {
    id: 'borrowed_funds_source',
    label: 'Source of borrowed funds',
    type: 'text',
    showIf: { undisclosed_borrowed_funds: true }
  },
  {
    id: 'borrowed_funds_amount',
    label: 'Amount to be borrowed',
    type: 'currency',
    showIf: { undisclosed_borrowed_funds: true }
  },
  {
    id: 'other_mortgage_application',
    question: 'Will you be applying for a mortgage on another property before closing?',
    type: 'boolean'
  },
  {
    id: 'priority_lien',
    question: 'Will this property be subject to a lien that could take priority?',
    type: 'boolean',
    helpText: 'Such as a second mortgage, HELOC, or lease'
  },
  {
    id: 'priority_lien_type',
    question: 'Type of lien',
    type: 'single-choice',
    options: [
      { value: 'second_mortgage', label: 'Second mortgage' },
      { value: 'heloc', label: 'Home equity line' },
      { value: 'lease', label: 'Lease' },
      { value: 'other', label: 'Other' }
    ],
    showIf: { priority_lien: true }
  }
];
```

---

### STAGE 7: GOVERNMENT MONITORING (85% Complete)

**Purpose:** Collect HMDA-required demographic information

#### Introduction Text

```javascript
const hmdaIntroduction = {
  title: 'Government Monitoring Information',
  content: `The purpose of collecting this information is to help ensure that all applicants 
  are treated fairly and that the housing needs of communities are being fulfilled. 
  
  Federal law requires that we ask applicants for their demographic information 
  (ethnicity, race, and sex) to monitor compliance with equal credit opportunity 
  and fair housing laws.
  
  You are not required to furnish this information, but are encouraged to do so. 
  The law provides that we may not discriminate on the basis of this information.`
};
```

#### For Each Borrower - Ethnicity

```javascript
const ethnicityQuestion = (borrowerIndex) => ({
  id: `borrower_${borrowerIndex}_ethnicity`,
  question: 'Ethnicity (Select one or more)',
  type: 'multi-choice',
  options: [
    {
      value: 'hispanic_latino',
      label: 'Hispanic or Latino',
      subOptions: [
        { value: 'mexican', label: 'Mexican' },
        { value: 'puerto_rican', label: 'Puerto Rican' },
        { value: 'cuban', label: 'Cuban' },
        { value: 'other_hispanic', label: 'Other Hispanic or Latino', hasTextField: true }
      ]
    },
    { value: 'not_hispanic_latino', label: 'Not Hispanic or Latino' },
    { value: 'no_provide', label: 'I do not wish to provide this information' }
  ],
  allowDecline: true
});
```

#### For Each Borrower - Race

```javascript
const raceQuestion = (borrowerIndex) => ({
  id: `borrower_${borrowerIndex}_race`,
  question: 'Race (Select all that apply)',
  type: 'multi-choice',
  options: [
    {
      value: 'american_indian',
      label: 'American Indian or Alaska Native',
      hasTextField: true,
      textFieldLabel: 'Name of enrolled or principal tribe (optional)'
    },
    {
      value: 'asian',
      label: 'Asian',
      subOptions: [
        { value: 'asian_indian', label: 'Asian Indian' },
        { value: 'chinese', label: 'Chinese' },
        { value: 'filipino', label: 'Filipino' },
        { value: 'japanese', label: 'Japanese' },
        { value: 'korean', label: 'Korean' },
        { value: 'vietnamese', label: 'Vietnamese' },
        { value: 'other_asian', label: 'Other Asian', hasTextField: true }
      ]
    },
    { value: 'black', label: 'Black or African American' },
    {
      value: 'pacific_islander',
      label: 'Native Hawaiian or Other Pacific Islander',
      subOptions: [
        { value: 'native_hawaiian', label: 'Native Hawaiian' },
        { value: 'guamanian', label: 'Guamanian or Chamorro' },
        { value: 'samoan', label: 'Samoan' },
        { value: 'other_pacific', label: 'Other Pacific Islander', hasTextField: true }
      ]
    },
    { value: 'white', label: 'White' },
    { value: 'no_provide', label: 'I do not wish to provide this information' }
  ],
  allowMultiple: true,
  allowDecline: true
});
```

#### For Each Borrower - Sex

```javascript
const sexQuestion = (borrowerIndex) => ({
  id: `borrower_${borrowerIndex}_sex`,
  question: 'Sex',
  type: 'single-choice',
  options: [
    { value: 'male', label: 'Male' },
    { value: 'female', label: 'Female' },
    { value: 'no_provide', label: 'I do not wish to provide this information' }
  ],
  allowDecline: true
});
```

---

### STAGE 8: SCHEDULE CONSULTATION (90% Complete)

**Purpose:** Schedule appointment with loan officer

```javascript
const scheduleConsultation = {
  preferredContactMethod: {
    id: 'preferred_contact_method',
    question: 'Preferred Contact Method',
    type: 'single-choice',
    options: [
      { value: 'phone', label: 'Phone call' },
      { value: 'video', label: 'Video call' },
      { value: 'in_person', label: 'In-person' }
    ]
  },
  additionalNotes: {
    id: 'consultation_notes',
    label: 'Additional Notes (optional)',
    type: 'textarea',
    maxLength: 500,
    placeholder: 'Any questions or special requests?'
  }
};

// Calendar integration - use Calendly or custom calendar component
```

---

### STAGE 9: AUTHORIZATIONS & CONSENT (95% Complete)

**Purpose:** Obtain credit authorization and e-consent signatures

#### Credit Authorization Agreement

```javascript
const creditAuthAgreement = {
  title: 'Credit Authorization',
  agreementText: `CREDIT AUTHORIZATION

I/We authorize [Company Name] and its affiliates to obtain credit reports and 
verify information concerning my/our credit, employment, income, and assets 
for the purpose of evaluating my/our loan application.

I/We understand that this authorization will remain in effect during the 
application process and for any subsequent modifications, renewals, or 
collections related to this loan.`,

  // For each borrower:
  signature: {
    fullName: '', // Pre-filled from application
    date: new Date(), // Auto-populated
    ipAddress: '', // Captured automatically
    checkbox: false // "I have read and agree to the Credit Authorization"
  }
};

// Validation: All borrowers must sign before proceeding
function validateCreditAuth(signatures) {
  return signatures.every(sig => sig.agreed && sig.signedAt);
}
```

#### E-Consent Documentation

```javascript
const eConsentAgreement = {
  title: 'Electronic Consent (E-Consent)',
  content: `ELECTRONIC SIGNATURES AND RECORDS CONSENT

By clicking "I Agree" below, you consent to:
1. Conduct transactions electronically
2. Receive all disclosures, notices, and documents electronically
3. Use electronic signatures with the same legal effect as handwritten signatures

System Requirements:
- Internet connection
- Current web browser (Chrome, Firefox, Safari, Edge)
- Valid email address
- Ability to download and save PDF files

Withdrawal of Consent:
You may withdraw your consent to conduct business electronically at any time.`,

  signature: {
    fullName: '', // Pre-filled
    date: new Date(), // Auto-populated
    email: '', // Pre-filled
    checkbox: false
  }
};
```

#### Final Submission

```javascript
const submitApplication = async (applicationData) => {
  // 1. Validate all signatures
  if (!validateAllSignatures(applicationData)) {
    throw new Error('All borrowers must sign both agreements');
  }

  // 2. Submit application
  const response = await fetch('/api/applications/submit', {
    method: 'POST',
    body: JSON.stringify(applicationData)
  });

  // 3. On success, redirect to client portal
  if (response.success) {
    // Wait 3 seconds to show success message
    await delay(3000);
    window.location.href = `/portal/dashboard?application_id=${response.id}&highlight=documents`;
  }
};
```

---

## Refinance Application Stages

### Key Differences from Purchase

1. **No Property Search** - Already own the property
2. **Current Mortgage Section** - New stage for existing loan details
3. **Refinance Goals** - Why refinancing, cash-out details
4. **Property Value vs Purchase Price** - Estimated current value
5. **No Real Estate Agent** - Not needed
6. **No Gift Funds** - Not applicable
7. **Different Document Requirements**

### Stage Overview

| Stage | Name | Progress % |
|-------|------|------------|
| 1 | About You | 10% |
| 2 | Your Property | 20% |
| 3 | Current Mortgage | 35% |
| 4 | Your Income | 50% |
| 5 | Your Assets | 60% |
| 6 | Real Estate Owned | 65% |
| 7 | Your Background | 80% |
| 8 | Government Monitoring | 85% |
| 9 | Schedule Consultation | 90% |
| 10 | Authorizations & Consent | 95% |

---

### REFINANCE STAGE 1: ABOUT YOU (Same as Purchase)

Identical to purchase application Stage 1

---

### REFINANCE STAGE 2: YOUR PROPERTY (20% Complete)

**Purpose:** Collect current home details and property information

#### Question 1: Property Confirmation

```javascript
// User's current address (subject property being refinanced)
// Display as confirmation from current residence in Stage 1

const propertyConfirmation = {
  id: 'subject_property_confirmation',
  type: 'confirmation',
  message: 'Is this the property you want to refinance?',
  displayAddress: `${currentResidence.street}, ${currentResidence.city}, ${currentResidence.state} ${currentResidence.zip}`,
  options: [
    { value: 'yes', label: 'Yes' },
    { value: 'different', label: 'No, different property' }
  ]
};

// If different, collect new address with Google Places autocomplete
```

#### Questions 2-3: Property Ownership

```javascript
const propertyOwnershipFields = [
  {
    id: 'time_owned_property_years',
    label: 'How long have you owned this property? (Years)',
    type: 'number',
    required: true,
    min: 0
  },
  {
    id: 'time_owned_property_months',
    label: 'Months',
    type: 'number',
    required: true,
    min: 0,
    max: 11
  }
];
```

#### Question 4: Property Type

```javascript
const refinancePropertyType = {
  id: 'property_type',
  question: 'What type of property is this?',
  type: 'single-choice',
  options: [
    { value: 'single_family', label: 'Single Family' },
    { value: 'condo', label: 'Condo' },
    { value: 'townhouse', label: 'Townhouse' },
    { value: 'multi_family', label: 'Multi-Family' }
  ],
  required: true
};
```

#### Question 5: Occupancy

```javascript
const refinanceOccupancy = {
  id: 'occupancy_type',
  question: 'How do you use this property?',
  type: 'single-choice',
  options: [
    { value: 'primary', label: 'Primary Residence' },
    { value: 'second_home', label: 'Second Home' },
    { value: 'investment', label: 'Investment/Rental' }
  ],
  required: true
};
```

#### Question 6: Property Value

```javascript
const propertyValueQuestion = {
  id: 'estimated_property_value',
  question: 'What do you estimate your property is currently worth?',
  type: 'currency',
  required: true,
  helpText: "This is your best estimate - we'll order an appraisal",
  validation: { min: 50000, max: 10000000 }
};
```

#### Questions 7-8: Property Taxes & Insurance

```javascript
const propertyExpensesFields = [
  {
    id: 'annual_property_tax',
    label: 'What is your annual property tax?',
    type: 'currency',
    allowUnknown: true // Checkbox: "Don't know / Included in mortgage payment"
  },
  {
    id: 'annual_insurance',
    label: 'What is your annual homeowners insurance?',
    type: 'currency',
    allowUnknown: true
  }
];
```

#### Questions 9-11: Home Improvements

```javascript
const homeImprovementQuestions = [
  {
    id: 'recent_home_improvements',
    question: 'Have you made any significant home improvements in the past 12 months?',
    type: 'boolean'
  },
  {
    id: 'improvements_made',
    question: 'What improvements did you make? (Check all that apply)',
    type: 'multi-choice',
    options: [
      { value: 'kitchen', label: 'Kitchen remodel' },
      { value: 'bathroom', label: 'Bathroom remodel' },
      { value: 'roof', label: 'New roof' },
      { value: 'hvac', label: 'New HVAC system' },
      { value: 'windows', label: 'New windows' },
      { value: 'flooring', label: 'Flooring' },
      { value: 'basement', label: 'Finished basement' },
      { value: 'addition', label: 'Room addition' },
      { value: 'outdoor', label: 'Pool/Deck/Patio' },
      { value: 'landscaping', label: 'Landscaping' },
      { value: 'other', label: 'Other (specify)' }
    ],
    showIf: { recent_home_improvements: true }
  },
  {
    id: 'improvements_total_cost',
    label: 'Total amount spent on improvements',
    type: 'currency',
    showIf: { recent_home_improvements: true }
  }
];
```

---

### REFINANCE STAGE 3: CURRENT MORTGAGE (35% Complete)

**Purpose:** Collect existing loan details and refinance goals

#### Question 1: Refinance Goals

```javascript
const refinanceGoalsQuestion = {
  id: 'refinance_goals',
  question: 'What are your main goals for refinancing? (Select all that apply)',
  type: 'multi-choice',
  options: [
    { value: 'lower_payment', label: 'Lower my monthly payment' },
    { value: 'lower_rate', label: 'Get a lower interest rate' },
    { value: 'shorter_term', label: 'Shorten my loan term' },
    { value: 'cash_out_improvements', label: 'Get cash out for home improvements' },
    { value: 'cash_out_debt', label: 'Get cash out for debt consolidation' },
    { value: 'cash_out_other', label: 'Get cash out for other needs' },
    { value: 'arm_to_fixed', label: 'Switch from ARM to fixed rate' },
    { value: 'remove_pmi', label: 'Remove PMI (mortgage insurance)' },
    { value: 'remove_borrower', label: 'Remove someone from the loan' }
  ],
  required: true,
  allowMultiple: true
};
```

#### Questions 2-4: Cash-Out Details

```javascript
const cashOutQuestions = [
  {
    id: 'wants_cash_out',
    question: 'Do you want to take cash out from your home equity?',
    type: 'single-choice',
    options: [
      { value: 'yes', label: 'Yes' },
      { value: 'maybe', label: 'Maybe' },
      { value: 'no', label: 'No' }
    ]
  },
  {
    id: 'cash_out_amount',
    label: 'How much cash would you like to receive?',
    type: 'currency',
    showIf: { wants_cash_out: ['yes', 'maybe'] },
    validation: {
      max: (data) => {
        // Max 80% LTV typically
        const maxLoanAmount = data.estimated_property_value * 0.80;
        return maxLoanAmount - data.current_loan_balance;
      }
    }
  },
  {
    id: 'cash_out_purpose',
    question: 'What will you use the cash for? (Select all that apply)',
    type: 'multi-choice',
    options: [
      { value: 'improvements', label: 'Home improvements/renovations' },
      { value: 'credit_cards', label: 'Pay off credit cards' },
      { value: 'other_debt', label: 'Pay off other debt' },
      { value: 'investment', label: 'Investment property down payment' },
      { value: 'education', label: 'Education expenses' },
      { value: 'emergency', label: 'Emergency fund' },
      { value: 'business', label: 'Business investment' },
      { value: 'other', label: 'Other' }
    ],
    showIf: { wants_cash_out: ['yes', 'maybe'] }
  }
];
```

#### Question 5: Statement Upload Option (Recommended)

```javascript
const statementUploadQuestion = {
  id: 'has_mortgage_statement',
  question: 'Can you upload your most recent mortgage statement?',
  type: 'single-choice',
  options: [
    { value: 'yes', label: "Yes, I have it" },
    { value: 'no', label: "No, I'll enter manually" }
  ],
  helpText: "This is the fastest way - we'll extract all your loan details automatically"
};

// If Yes → Same Upload & Parse Flow as REO Properties using Claude Vision
```

#### Manual Entry: Current Mortgage Fields

```javascript
const currentMortgageManualFields = [
  {
    id: 'current_lender_name',
    label: 'Who is your current mortgage lender or servicer?',
    type: 'text',
    autocomplete: 'lender-list', // Common lenders
    required: true,
    examples: ['Wells Fargo', 'Chase', 'Quicken Loans', 'Bank of America']
  },
  {
    id: 'loan_number',
    label: 'Loan Number (optional)',
    type: 'text',
    optional: true
  },
  {
    id: 'current_loan_balance',
    label: 'Current Loan Balance',
    type: 'currency',
    required: true
  },
  {
    id: 'current_interest_rate',
    label: 'Current Interest Rate',
    type: 'percentage',
    required: true,
    decimals: 3 // e.g., 6.875%
  },
  {
    id: 'current_monthly_pi',
    label: 'Current Monthly Payment (Principal & Interest only)',
    type: 'currency',
    required: true
  },
  {
    id: 'monthly_escrow',
    label: 'Monthly Escrow Payment (if applicable)',
    type: 'currency',
    allowNone: true // Checkbox: "No escrow account"
  }
];

// If Has Escrow:
const escrowBreakdownFields = [
  {
    id: 'escrow_property_tax',
    label: 'Monthly property taxes (from escrow)',
    type: 'currency',
    showIf: (data) => data.monthly_escrow > 0
  },
  {
    id: 'escrow_insurance',
    label: 'Monthly homeowners insurance (from escrow)',
    type: 'currency'
  },
  {
    id: 'escrow_hoa',
    label: 'Monthly HOA fees (if escrowed)',
    type: 'currency',
    optional: true
  }
];
```

#### Original Loan Information

```javascript
const originalLoanFields = [
  {
    id: 'original_loan_amount',
    label: 'Original Loan Amount',
    type: 'currency',
    required: true
  },
  {
    id: 'loan_origination_date',
    label: 'When did you get your current mortgage?',
    type: 'month-year',
    required: true
  },
  {
    id: 'current_loan_type',
    question: 'What type of loan do you currently have?',
    type: 'single-choice',
    options: [
      { value: '30_fixed', label: '30-Year Fixed' },
      { value: '20_fixed', label: '20-Year Fixed' },
      { value: '15_fixed', label: '15-Year Fixed' },
      { value: '10_fixed', label: '10-Year Fixed' },
      { value: '5_1_arm', label: '5/1 ARM' },
      { value: '7_1_arm', label: '7/1 ARM' },
      { value: '10_1_arm', label: '10/1 ARM' },
      { value: 'fha', label: 'FHA' },
      { value: 'va', label: 'VA' },
      { value: 'usda', label: 'USDA' },
      { value: 'other', label: 'Other' }
    ],
    required: true
  }
];

// If ARM:
const armFields = [
  {
    id: 'next_rate_adjustment',
    label: 'When is your next rate adjustment?',
    type: 'month-year',
    showIf: { current_loan_type: ['5_1_arm', '7_1_arm', '10_1_arm'] }
  },
  {
    id: 'rate_cap',
    label: 'What is your rate cap? (optional)',
    type: 'percentage',
    optional: true
  }
];
```

#### Second Mortgage / HELOC

```javascript
const secondMortgageQuestions = [
  {
    id: 'has_second_mortgage',
    question: 'Do you have a second mortgage or HELOC?',
    type: 'boolean'
  },
  {
    id: 'second_lien_type',
    question: 'Type of second lien',
    type: 'single-choice',
    options: [
      { value: 'second_mortgage', label: 'Second Mortgage' },
      { value: 'heloc', label: 'HELOC' }
    ],
    showIf: { has_second_mortgage: true }
  },
  {
    id: 'second_lien_lender',
    label: 'Lender/Servicer Name',
    type: 'text',
    required: true,
    showIf: { has_second_mortgage: true }
  },
  {
    id: 'second_lien_balance',
    label: 'Current Balance',
    type: 'currency',
    required: true,
    showIf: { has_second_mortgage: true }
  },
  {
    id: 'second_lien_payment',
    label: 'Monthly Payment',
    type: 'currency',
    required: true,
    showIf: { has_second_mortgage: true }
  },
  {
    id: 'second_lien_rate',
    label: 'Interest Rate',
    type: 'percentage',
    showIf: { has_second_mortgage: true }
  },
  // HELOC Specific:
  {
    id: 'heloc_credit_limit',
    label: 'Credit Limit',
    type: 'currency',
    showIf: { second_lien_type: 'heloc' }
  },
  {
    id: 'payoff_second_lien',
    question: 'Do you want to pay off the second mortgage/HELOC with this refinance?',
    type: 'boolean',
    showIf: { has_second_mortgage: true }
  }
];
```

#### Payment History

```javascript
const paymentHistoryQuestions = [
  {
    id: 'on_time_payments',
    question: 'Have you made all mortgage payments on time in the past 12 months?',
    type: 'boolean'
  },
  {
    id: 'late_payment_count',
    question: 'How many payments were late?',
    type: 'single-choice',
    options: [
      { value: '1', label: '1' },
      { value: '2', label: '2' },
      { value: '3', label: '3' },
      { value: '4+', label: '4+' }
    ],
    showIf: { on_time_payments: false }
  },
  {
    id: 'most_recent_late_payment',
    question: 'When was the most recent late payment?',
    type: 'single-choice',
    options: [
      { value: '<3mo', label: 'Within last 3 months' },
      { value: '3-6mo', label: '3-6 months ago' },
      { value: '6-12mo', label: '6-12 months ago' }
    ],
    showIf: { on_time_payments: false }
  }
];
```

---

### REFINANCE STAGES 4-10

**Stage 4: Your Income** - Same as Purchase

**Stage 5: Your Assets** - Simplified (primarily for cash-out, reserves, or closing costs)

**Stage 6: Real Estate Owned** - Same as Purchase (OTHER properties only)

**Stage 7: Your Background** - Same as Purchase, except:
- Remove previous home questions
- Remove gift funds questions

**Stages 8-10: HMDA, Schedule, Authorizations** - Same as Purchase

---

## Autocomplete Integrations

### Integration 1: Google Places - Employer Autocomplete

**Where Used:** Stage 3 (Your Income) - Employer Name field

```javascript
// hooks/usePlacesAutocomplete.js

import { useState, useEffect } from 'react';
import { useDebounce } from './useDebounce';

export function usePlacesAutocomplete({ query, types = ['establishment'], debounceMs = 300 }) {
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const debouncedQuery = useDebounce(query, debounceMs);

  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 3) {
      setSuggestions([]);
      return;
    }

    const fetchSuggestions = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('/api/places/autocomplete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input: debouncedQuery, types })
        });

        const data = await response.json();
        setSuggestions(data.predictions || []);
      } catch (error) {
        console.error('Error fetching places:', error);
        setSuggestions([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSuggestions();
  }, [debouncedQuery, types]);

  const getPlaceDetails = async (placeId) => {
    const response = await fetch('/api/places/details', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ placeId })
    });

    const data = await response.json();
    return data.result;
  };

  return { suggestions, isLoading, getPlaceDetails };
}
```

```javascript
// hooks/useDebounce.js

import { useState, useEffect } from 'react';

export function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}
```

### Integration 2: Google Places - Property Address Autocomplete

**Where Used:**
- Stage 2 (New Home) - Property Address fields
- Stage 5 (Real Estate Owned) - Each property address

```javascript
// components/PropertyAddressAutocomplete.js

import { useState } from 'react';
import { usePlacesAutocomplete } from '../hooks/usePlacesAutocomplete';

export function PropertyAddressAutocomplete({ onAddressSelect, initialValue = '' }) {
  const [query, setQuery] = useState(initialValue);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [showResults, setShowResults] = useState(false);

  const { suggestions, isLoading, getPlaceDetails } = usePlacesAutocomplete({
    query,
    types: ['address'],
    debounceMs: 300
  });

  const handleSelect = async (placeId) => {
    const details = await getPlaceDetails(placeId);
    const addressComponents = parseAddressComponents(details.address_components);

    const addressData = {
      streetAddress: `${addressComponents.street_number || ''} ${addressComponents.route || ''}`.trim(),
      city: addressComponents.locality || addressComponents.sublocality || '',
      state: addressComponents.administrative_area_level_1 || '',
      zipCode: addressComponents.postal_code || '',
      formattedAddress: details.formatted_address,
      placeId: placeId,
      latitude: details.geometry.location.lat,
      longitude: details.geometry.location.lng
    };

    setSelectedAddress(addressData);
    setQuery(details.formatted_address);
    setShowResults(false);
    onAddressSelect(addressData);
  };

  return (
    <div className="space-y-4">
      <div className="relative">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Property Address
        </label>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowResults(true);
            setSelectedAddress(null);
          }}
          onFocus={() => setShowResults(true)}
          placeholder="Start typing the property address..."
          className="w-full px-4 py-2 border border-gray-300 rounded-lg"
        />

        {showResults && suggestions.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-96 overflow-y-auto">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion.place_id}
                onClick={() => handleSelect(suggestion.place_id)}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 border-b"
              >
                <div className="font-medium">{suggestion.structured_formatting.main_text}</div>
                <div className="text-sm text-gray-500">{suggestion.structured_formatting.secondary_text}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedAddress && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Street Address</label>
            <input type="text" value={selectedAddress.streetAddress} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">City</label>
            <input type="text" value={selectedAddress.city} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">State</label>
            <input type="text" value={selectedAddress.state} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">ZIP Code</label>
            <input type="text" value={selectedAddress.zipCode} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
        </div>
      )}
    </div>
  );
}

function parseAddressComponents(components) {
  const result = {};

  components.forEach(component => {
    const types = component.types;

    if (types.includes('street_number')) result.street_number = component.long_name;
    if (types.includes('route')) result.route = component.long_name;
    if (types.includes('locality')) result.locality = component.long_name;
    if (types.includes('sublocality')) result.sublocality = component.long_name;
    if (types.includes('administrative_area_level_1')) result.administrative_area_level_1 = component.short_name;
    if (types.includes('postal_code')) result.postal_code = component.long_name;
  });

  return result;
}
```

### Integration 3: CRM - Real Estate Agent Autocomplete

**Where Used:** Stage 2 (New Home) - Real Estate Agent fields (Purchase only)

```javascript
// components/RealtorAutocomplete.js

import { useState, useEffect } from 'react';

export function RealtorAutocomplete({ onRealtorSelect, initialValue = '' }) {
  const [query, setQuery] = useState(initialValue);
  const [realtors, setRealtors] = useState([]);
  const [selectedRealtor, setSelectedRealtor] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [showManualEntry, setShowManualEntry] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!query || query.length < 2) {
      setRealtors([]);
      return;
    }

    const searchRealtors = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('/api/realtors/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query })
        });

        const data = await response.json();
        setRealtors(data.realtors || []);
      } catch (error) {
        console.error('Error searching realtors:', error);
        setRealtors([]);
      } finally {
        setIsLoading(false);
      }
    };

    const debounceTimer = setTimeout(searchRealtors, 300);
    return () => clearTimeout(debounceTimer);
  }, [query]);

  const handleSelect = (realtor) => {
    setSelectedRealtor(realtor);
    setQuery(realtor.name);
    setShowResults(false);
    onRealtorSelect(realtor);
  };

  if (showManualEntry) {
    return (
      <ManualRealtorEntry
        onSubmit={(realtorData) => {
          setSelectedRealtor(realtorData);
          setShowManualEntry(false);
          onRealtorSelect(realtorData);
        }}
        onCancel={() => setShowManualEntry(false)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <label className="block text-sm font-medium mb-2">Real Estate Agent Name</label>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowResults(true);
            setSelectedRealtor(null);
          }}
          onFocus={() => setShowResults(true)}
          placeholder="Start typing agent name..."
          className="w-full px-4 py-2 border rounded-lg"
        />

        {showResults && !selectedRealtor && (
          <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-96 overflow-y-auto">
            {isLoading && <div className="px-4 py-3 text-gray-500">Searching...</div>}

            {!isLoading && realtors.length === 0 && query.length >= 2 && (
              <div className="px-4 py-3">
                <p className="text-gray-600 mb-2">No agents found in our network</p>
                <button onClick={() => setShowManualEntry(true)} className="text-blue-600 font-medium text-sm">
                  Enter agent information manually →
                </button>
              </div>
            )}

            {realtors.map((realtor) => (
              <button
                key={realtor.id}
                onClick={() => handleSelect(realtor)}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 border-b"
              >
                <div className="font-semibold">{realtor.name}</div>
                <div className="text-sm text-gray-600">{realtor.email} • {realtor.phone}</div>
                <div className="text-sm text-gray-500">{realtor.company}</div>
              </button>
            ))}

            {realtors.length > 0 && (
              <button onClick={() => setShowManualEntry(true)} className="w-full px-4 py-3 text-center text-sm text-gray-600 hover:bg-gray-50">
                Not in list? Enter manually
              </button>
            )}
          </div>
        )}
      </div>

      {selectedRealtor && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Agent Phone</label>
            <input type="tel" value={selectedRealtor.phone} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Agent Email</label>
            <input type="email" value={selectedRealtor.email} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-2">Agent Company</label>
            <input type="text" value={selectedRealtor.company} className="w-full px-4 py-2 border rounded-lg" readOnly />
          </div>
        </div>
      )}
    </div>
  );
}

function ManualRealtorEntry({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({ name: '', phone: '', email: '', company: '' });

  const handleSubmit = () => {
    onSubmit({ ...formData, isInCRM: false });
  };

  const isValid = formData.name && formData.phone && formData.email && formData.company;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Enter Agent Information</h3>
        <button onClick={onCancel} className="text-gray-600 text-sm">← Back to search</button>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Agent Name *</label>
        <input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className="w-full px-4 py-2 border rounded-lg" required />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-2">Phone *</label>
          <input type="tel" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} className="w-full px-4 py-2 border rounded-lg" required />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Email *</label>
          <input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className="w-full px-4 py-2 border rounded-lg" required />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Company *</label>
        <input type="text" value={formData.company} onChange={(e) => setFormData({ ...formData, company: e.target.value })} className="w-full px-4 py-2 border rounded-lg" required />
      </div>

      <button onClick={handleSubmit} disabled={!isValid} className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300">
        Continue
      </button>
    </div>
  );
}
```

---

## Database Schema

### Applications Table

```sql
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Application Type & Status
    application_type TEXT NOT NULL CHECK (application_type IN ('purchase', 'refinance')),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'processing', 'underwriting', 'approved', 'denied', 'closed')),

    -- Progress Tracking
    current_stage INTEGER DEFAULT 1,
    completion_percentage INTEGER DEFAULT 0,
    stages_completed JSONB DEFAULT '[]'::jsonb,

    -- Borrower Information
    borrower_count INTEGER DEFAULT 1,
    borrower_relationship TEXT,

    -- Military/VA
    veteran_status TEXT,
    va_loan_history TEXT,
    va_disability TEXT,

    -- Property Information (Purchase)
    property_state TEXT,
    property_city_area TEXT,
    property_search_status TEXT,
    closing_date_range TEXT,
    property_type TEXT,
    number_of_units INTEGER,
    occupancy_type TEXT,
    first_time_buyer BOOLEAN,

    -- Property Address (if known)
    property_street TEXT,
    property_city TEXT,
    property_state_actual TEXT,
    property_zip TEXT,
    mls_number TEXT,
    property_place_id TEXT,
    property_latitude DECIMAL(10, 8),
    property_longitude DECIMAL(11, 8),

    -- Budget (Purchase)
    purchase_price DECIMAL(12,2),
    down_payment DECIMAL(12,2),
    down_payment_percentage DECIMAL(5,2),
    loan_amount DECIMAL(12,2),

    -- Property Details
    monthly_hoa_fee DECIMAL(10,2),
    hoa_name TEXT,
    estimated_annual_property_tax DECIMAL(10,2),
    estimated_annual_insurance DECIMAL(10,2),

    -- Real Estate Agent (Purchase only)
    has_realtor BOOLEAN,
    realtor_id UUID REFERENCES realtors(id),
    realtor_name TEXT,
    realtor_phone TEXT,
    realtor_email TEXT,
    realtor_company TEXT,
    realtor_in_crm BOOLEAN DEFAULT FALSE,

    -- Refinance-Specific Fields
    estimated_property_value DECIMAL(12,2),
    time_owned_property_years INTEGER,
    time_owned_property_months INTEGER,
    recent_home_improvements BOOLEAN,
    improvements_made TEXT[],
    improvements_total_cost DECIMAL(12,2),

    -- Refinance Goals
    refinance_goals TEXT[],
    wants_cash_out TEXT,
    cash_out_amount DECIMAL(12,2),
    cash_out_purpose TEXT[],

    -- Assets
    checking_total DECIMAL(12,2),
    savings_total DECIMAL(12,2),
    investments_total DECIMAL(12,2),
    retirement_total DECIMAL(12,2),

    -- Gift Funds
    using_gift_funds TEXT,
    gift_amount DECIMAL(12,2),
    gift_donor_relationship TEXT,
    gift_donor_name TEXT,

    -- Background/Declarations
    owns_other_property BOOLEAN,
    previous_home_status TEXT,
    foreclosure_date TEXT,
    deed_in_lieu BOOLEAN,
    deed_in_lieu_date TEXT,

    -- Monthly Obligations
    pays_alimony_child_support BOOLEAN,
    monthly_alimony_child_support_paid DECIMAL(10,2),
    alimony_child_support_type_paid TEXT,
    alimony_child_support_duration_remaining TEXT,
    has_childcare_expenses BOOLEAN,
    monthly_childcare_expense DECIMAL(10,2),

    -- Tax & Debt
    irs_debt TEXT,
    irs_monthly_payment DECIMAL(10,2),
    irs_payment_current TEXT,
    federal_debt_delinquent BOOLEAN,
    federal_debt_type TEXT,

    -- Credit History
    recent_credit_applications BOOLEAN,
    credit_application_type TEXT,
    credit_application_status TEXT,
    credit_challenges TEXT,
    bankruptcy_type TEXT,
    bankruptcy_discharge_date TEXT,
    chapter_13_status TEXT,

    -- Legal Issues
    lawsuit_or_judgment BOOLEAN,
    lawsuit_description TEXT,

    -- Transaction Declarations
    seller_relationship TEXT,
    seller_relationship_description TEXT,
    undisclosed_borrowed_funds BOOLEAN,
    borrowed_funds_source TEXT,
    borrowed_funds_amount DECIMAL(12,2),
    other_mortgage_application BOOLEAN,
    other_mortgage_property_address TEXT,
    other_mortgage_purpose TEXT,
    priority_lien BOOLEAN,
    priority_lien_type TEXT,

    -- Consultation
    consultation_scheduled_at TIMESTAMPTZ,
    consultation_loan_officer TEXT,
    consultation_contact_method TEXT,
    consultation_notes TEXT,

    -- Authorizations
    credit_auth_signed BOOLEAN DEFAULT FALSE,
    credit_auth_signed_at TIMESTAMPTZ,
    credit_auth_ip_address INET,
    econsent_signed BOOLEAN DEFAULT FALSE,
    econsent_signed_at TIMESTAMPTZ,
    econsent_ip_address INET,

    -- Submission
    submitted_at TIMESTAMPTZ,
    submitted_from_ip INET,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    assigned_lo UUID REFERENCES users(id)
);

CREATE INDEX idx_applications_type ON applications(application_type);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_created ON applications(created_at);
CREATE INDEX idx_applications_lo ON applications(assigned_lo);
```

### Borrowers Table

```sql
CREATE TABLE borrowers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,

    -- Borrower Sequence
    borrower_sequence INTEGER NOT NULL, -- 0 = primary, 1+ = co-borrowers
    is_primary BOOLEAN DEFAULT FALSE,

    -- Personal Information
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    ssn_encrypted TEXT NOT NULL,
    ssn_last_4 TEXT,

    -- Citizenship & Marital Status
    citizenship_status TEXT NOT NULL,
    marital_status TEXT NOT NULL,
    spouse_first_name TEXT,
    spouse_last_name TEXT,
    spouse_on_loan BOOLEAN,
    divorce_finalized TEXT,

    -- Income (Child Support/Alimony Received)
    receives_alimony_child_support BOOLEAN,
    monthly_alimony_child_support_received DECIMAL(10,2),
    alimony_child_support_duration TEXT,
    alimony_child_support_type_received TEXT,

    -- HMDA Demographics
    hmda_ethnicity JSONB,
    hmda_ethnicity_other TEXT,
    hmda_race JSONB,
    hmda_race_other TEXT,
    hmda_sex TEXT,
    hmda_declined BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_borrower_sequence UNIQUE(application_id, borrower_sequence)
);

CREATE INDEX idx_borrowers_application ON borrowers(application_id);
CREATE INDEX idx_borrowers_email ON borrowers(email);
```

### Borrower Addresses Table

```sql
CREATE TABLE borrower_addresses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    borrower_id UUID REFERENCES borrowers(id) ON DELETE CASCADE,

    address_type TEXT NOT NULL CHECK (address_type IN ('current', 'previous')),
    address_sequence INTEGER DEFAULT 0,

    street_address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,

    time_at_address_years INTEGER NOT NULL,
    time_at_address_months INTEGER NOT NULL,

    housing_status TEXT NOT NULL CHECK (housing_status IN ('own', 'rent', 'living_rent_free')),
    monthly_housing_payment DECIMAL(10,2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_duration CHECK (
        time_at_address_years >= 0 AND
        time_at_address_months >= 0 AND
        time_at_address_months < 12
    )
);

CREATE INDEX idx_addresses_borrower ON borrower_addresses(borrower_id);
```

### Borrower Employment Table

```sql
CREATE TABLE borrower_employment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    borrower_id UUID REFERENCES borrowers(id) ON DELETE CASCADE,

    employment_type TEXT NOT NULL CHECK (employment_type IN ('current', 'previous', 'second_job')),
    employment_status TEXT NOT NULL CHECK (employment_status IN ('w2_employee', 'self_employed', 'side_business')),

    -- W-2 Employee Fields
    employer_name TEXT,
    employer_address TEXT,
    employer_phone TEXT,
    employer_place_id TEXT,
    job_title TEXT,
    employment_start_date DATE,
    employment_end_date DATE,
    annual_base_salary DECIMAL(12,2),

    -- Self-Employed Fields
    self_employment_duration TEXT,
    business_structure TEXT,
    filed_tax_returns TEXT,
    write_off_expenses TEXT,
    business_name TEXT,
    business_type TEXT,
    ownership_percentage DECIMAL(5,2),
    annual_net_income DECIMAL(12,2),

    -- Additional Income
    has_additional_income BOOLEAN DEFAULT FALSE,
    monthly_rental_income DECIMAL(10,2),
    other_monthly_income DECIMAL(10,2),
    other_income_source TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_employment_borrower ON borrower_employment(borrower_id);
```

### Real Estate Owned Table

```sql
CREATE TABLE application_real_estate_owned (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    borrower_id UUID REFERENCES borrowers(id),
    property_sequence INTEGER NOT NULL,

    -- Property Details
    street_address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    property_place_id TEXT,
    property_type TEXT,
    occupancy_status TEXT NOT NULL,
    current_market_value DECIMAL(12,2),

    -- Mortgage Info
    has_mortgage BOOLEAN DEFAULT TRUE,
    lender_name TEXT,
    loan_number TEXT,
    loan_balance DECIMAL(12,2),
    monthly_pi_payment DECIMAL(10,2),
    monthly_property_tax DECIMAL(10,2),
    monthly_insurance DECIMAL(10,2),
    monthly_hoa DECIMAL(10,2) DEFAULT 0,
    interest_rate DECIMAL(5,3),
    loan_type TEXT,

    -- Rental Info
    is_rental BOOLEAN DEFAULT FALSE,
    monthly_rental_income DECIMAL(10,2),
    has_lease_in_place BOOLEAN,

    -- Data Source
    data_source TEXT NOT NULL CHECK (data_source IN ('mortgage_statement', 'manual_entry')),
    mortgage_statement_path TEXT,
    statement_confidence_score DECIMAL(3,2),
    manually_verified BOOLEAN DEFAULT FALSE,

    -- Calculated Fields
    total_monthly_payment DECIMAL(10,2) GENERATED ALWAYS AS (
        COALESCE(monthly_pi_payment, 0) +
        COALESCE(monthly_property_tax, 0) +
        COALESCE(monthly_insurance, 0) +
        COALESCE(monthly_hoa, 0)
    ) STORED,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reo_application ON application_real_estate_owned(application_id);
```

### Current Mortgages Table (Refinance Only)

```sql
CREATE TABLE current_mortgages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,

    lender_servicer_name TEXT NOT NULL,
    loan_number TEXT,

    current_balance DECIMAL(12,2) NOT NULL,
    interest_rate DECIMAL(5,3) NOT NULL,
    monthly_pi_payment DECIMAL(10,2) NOT NULL,
    monthly_escrow DECIMAL(10,2),
    monthly_property_tax DECIMAL(10,2),
    monthly_insurance DECIMAL(10,2),
    monthly_hoa DECIMAL(10,2),

    original_loan_amount DECIMAL(12,2),
    origination_date DATE,
    loan_type TEXT,

    -- ARM Details
    next_rate_adjustment DATE,
    rate_cap DECIMAL(5,3),

    -- Payment History
    late_payments_12_months INTEGER DEFAULT 0,
    last_late_payment_date DATE,
    on_time_payments BOOLEAN DEFAULT TRUE,

    -- Data Source
    statement_path TEXT,
    statement_confidence_score DECIMAL(3,2),
    data_source TEXT DEFAULT 'manual' CHECK (data_source IN ('statement_upload', 'manual')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_current_mortgage_app ON current_mortgages(application_id);
```

### Second Mortgages Table (Refinance Only)

```sql
CREATE TABLE second_mortgages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,

    lien_type TEXT NOT NULL CHECK (lien_type IN ('second_mortgage', 'heloc')),
    lender_servicer_name TEXT NOT NULL,
    current_balance DECIMAL(12,2) NOT NULL,
    monthly_payment DECIMAL(10,2),
    interest_rate DECIMAL(5,3),

    -- HELOC Specific
    credit_limit DECIMAL(12,2),
    amount_drawn DECIMAL(12,2),

    payoff_at_closing BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_second_mortgage_app ON second_mortgages(application_id);
```

### Realtors Table (CRM)

```sql
CREATE TABLE realtors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    company TEXT NOT NULL,
    license_number TEXT,
    license_state TEXT,
    source TEXT DEFAULT 'manual',
    is_active BOOLEAN DEFAULT TRUE,
    total_referrals INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_email UNIQUE(email)
);

-- Enable trigram extension for fuzzy searching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_realtor_name ON realtors USING gin(name gin_trgm_ops);
CREATE INDEX idx_realtor_email ON realtors(email);
CREATE INDEX idx_realtor_phone ON realtors(phone);
CREATE INDEX idx_realtor_company ON realtors USING gin(company gin_trgm_ops);
```

### Application Documents Table

```sql
CREATE TABLE application_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,

    document_type TEXT NOT NULL,
    document_category TEXT NOT NULL,
    file_path TEXT,
    file_name TEXT,
    file_size INTEGER,
    mime_type TEXT,

    uploaded_at TIMESTAMPTZ,
    uploaded_by UUID REFERENCES users(id),

    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'uploaded', 'under_review', 'approved', 'needs_revision')),
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,

    is_required BOOLEAN DEFAULT TRUE,
    display_order INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_app_docs ON application_documents(application_id);
CREATE INDEX idx_doc_status ON application_documents(status);
```

---

## Backend API Endpoints

### Google Places API Endpoints

```python
# api/routes/google_places.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os

router = APIRouter(prefix="/api/places", tags=["Google Places"])

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

class PlacesAutocompleteRequest(BaseModel):
    input: str
    types: Optional[List[str]] = ["establishment"]

class PlaceDetailsRequest(BaseModel):
    placeId: str

@router.post("/autocomplete")
async def autocomplete_places(request: PlacesAutocompleteRequest):
    """Get autocomplete suggestions from Google Places API"""
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

    params = {
        "input": request.input,
        "types": "|".join(request.types) if request.types else "establishment",
        "key": GOOGLE_PLACES_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise HTTPException(500, "Failed to fetch places")

        return response.json()


@router.post("/details")
async def get_place_details(request: PlaceDetailsRequest):
    """Get detailed information about a specific place"""
    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": request.placeId,
        "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
        "key": GOOGLE_PLACES_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise HTTPException(500, "Failed to fetch place details")

        return response.json()
```

### CRM Realtor API Endpoints

```python
# api/routes/realtors.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

router = APIRouter(prefix="/api/realtors", tags=["Realtors"])

class RealtorSearchRequest(BaseModel):
    query: str

class CreateRealtorRequest(BaseModel):
    name: str
    phone: str
    email: str
    company: str

@router.post("/search")
async def search_realtors(request: RealtorSearchRequest, db: Session = Depends(get_db)):
    """Search for realtors in CRM database with fuzzy matching"""
    query = request.query.lower()

    realtors = db.query(Realtor).filter(
        or_(
            Realtor.name.ilike(f"%{query}%"),
            Realtor.email.ilike(f"%{query}%"),
            Realtor.phone.ilike(f"%{query}%"),
            Realtor.company.ilike(f"%{query}%")
        )
    ).filter(
        Realtor.is_active == True
    ).limit(10).all()

    results = []
    for realtor in realtors:
        results.append({
            "id": str(realtor.id),
            "name": realtor.name,
            "phone": format_phone_number(realtor.phone),
            "email": realtor.email,
            "company": realtor.company,
            "isInCRM": True
        })

    return {"realtors": results}


@router.post("/create")
async def create_realtor(request: CreateRealtorRequest, db: Session = Depends(get_db)):
    """Create new realtor record in CRM"""
    # Check if realtor already exists
    existing = db.query(Realtor).filter(
        or_(
            Realtor.email == request.email,
            Realtor.phone == request.phone
        )
    ).first()

    if existing:
        return {"id": str(existing.id), "message": "Agent already exists"}

    new_realtor = Realtor(
        name=request.name,
        phone=request.phone,
        email=request.email,
        company=request.company,
        source="application_entry"
    )

    db.add(new_realtor)
    db.commit()
    db.refresh(new_realtor)

    return {"id": str(new_realtor.id), "message": "New agent added"}


def format_phone_number(phone):
    """Format phone number as (XXX) XXX-XXXX"""
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone
```

### Document Parsing API (Claude Vision)

```python
# api/routes/document_parsing.py

from fastapi import APIRouter, UploadFile, File, HTTPException
import anthropic
import base64
import json
import os

router = APIRouter(prefix="/api/documents", tags=["Document Parsing"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

@router.post("/parse-mortgage-statement")
async def parse_mortgage_statement(file: UploadFile = File(...), application_id: str = None):
    """Upload and parse mortgage statement using Claude AI"""

    # Validate file type
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Invalid file type. Please upload PDF, JPG, or PNG")

    # Validate file size (max 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Maximum size is 10MB")

    try:
        # 1. Upload to storage (implement your storage solution)
        file_path = await upload_to_storage(contents, file.filename, f"applications/{application_id}/statements")

        # 2. Parse with Claude
        parsed_data = await parse_statement_with_claude(contents, file.content_type)

        # 3. Validate parsed data
        if not parsed_data or parsed_data.get('confidence', {}).get('overall', 0) < 50:
            return {
                "status": "low_confidence",
                "message": "We had trouble reading this statement. Please enter manually.",
                "data": parsed_data,
                "file_path": file_path
            }

        # 4. Calculate total monthly payment
        parsed_data['total_monthly_payment'] = (
            parsed_data.get('monthly_pi_payment', 0) +
            parsed_data.get('monthly_property_tax', 0) +
            parsed_data.get('monthly_insurance', 0) +
            parsed_data.get('monthly_hoa', 0)
        )

        return {
            "status": "success",
            "message": "Statement parsed successfully",
            "data": parsed_data,
            "file_path": file_path,
            "confidence": parsed_data['confidence'],
            "requires_review": parsed_data['confidence']['overall'] < 80
        }

    except Exception as e:
        raise HTTPException(500, f"Failed to parse mortgage statement: {str(e)}")


async def parse_statement_with_claude(file_content, content_type):
    """Use Claude Vision to extract structured data from mortgage statement"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Prepare content based on file type
    if content_type == 'application/pdf':
        content_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(file_content).decode()
            }
        }
    else:
        content_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": base64.b64encode(file_content).decode()
            }
        }

    prompt = """
    Analyze this mortgage statement and extract the following information.
    Return ONLY valid JSON with no markdown code fences.

    Extract these fields:
    {
        "property_address": {
            "street": "string",
            "city": "string",
            "state": "string (2-letter code)",
            "zip": "string"
        },
        "lender_name": "string",
        "loan_number": "string",
        "current_balance": number,
        "monthly_pi_payment": number,
        "monthly_property_tax": number,
        "monthly_insurance": number,
        "monthly_hoa": number,
        "interest_rate": number,
        "original_loan_amount": number,
        "origination_date": "YYYY-MM-DD",
        "loan_type": "string",
        "confidence": {
            "overall": number (0-100),
            "property_address": number,
            "payment_amounts": number,
            "loan_balance": number
        }
    }

    Important:
    - All monetary amounts should be MONTHLY, not annual
    - If you see annual amounts, divide by 12
    - Use null for fields you cannot extract
    - Confidence: 90-100=very clear, 70-89=reasonably clear, 50-69=unclear, 0-49=cannot determine
    """

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [content_block, {"type": "text", "text": prompt}]
            }]
        )

        json_text = response.content[0].text.strip()
        json_text = json_text.replace("```json", "").replace("```", "").strip()

        return json.loads(json_text)

    except Exception as e:
        return {"confidence": {"overall": 0}, "error": str(e)}


async def upload_to_storage(file_content, filename, path):
    """Upload file to storage (implement your solution - S3, Cloud Storage, etc.)"""
    # TODO: Implement your file storage logic
    return f"{path}/{filename}"
```

---

## 7. Document Checklist Generation

The document checklist should be dynamically generated based on application answers. This provides borrowers with a personalized list of required documents.

### Python Backend - Document Checklist Generator

```python
# backend/services/document_checklist_service.py

from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

class DocumentCategory(Enum):
    INCOME = "income"
    ASSETS = "assets"
    PROPERTY = "property"
    IDENTITY = "identity"
    CREDIT = "credit"
    OTHER = "other"

class DocumentPriority(Enum):
    REQUIRED = "required"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"

@dataclass
class DocumentRequirement:
    id: str
    name: str
    description: str
    category: DocumentCategory
    priority: DocumentPriority
    count: int = 1  # Number of documents needed (e.g., 2 paystubs)
    time_period: Optional[str] = None  # e.g., "60 days", "2 years"
    notes: Optional[str] = None

def generate_document_checklist(application_data: Dict) -> List[DocumentRequirement]:
    """
    Generate personalized document checklist based on application answers.
    
    Args:
        application_data: Dictionary containing all application answers
        
    Returns:
        List of DocumentRequirement objects
    """
    checklist = []
    
    # =========================================
    # IDENTITY DOCUMENTS (Always Required)
    # =========================================
    checklist.append(DocumentRequirement(
        id="drivers_license",
        name="Driver's License or State ID",
        description="Valid government-issued photo identification",
        category=DocumentCategory.IDENTITY,
        priority=DocumentPriority.REQUIRED,
        notes="Front and back, not expired"
    ))
    
    checklist.append(DocumentRequirement(
        id="ssn_card",
        name="Social Security Card",
        description="Social Security card for all borrowers",
        category=DocumentCategory.IDENTITY,
        priority=DocumentPriority.REQUIRED
    ))
    
    # =========================================
    # INCOME DOCUMENTS
    # =========================================
    employment_type = application_data.get('employment_type')
    
    # W-2 Employees
    if employment_type in ['employed', 'full_time', 'part_time']:
        checklist.append(DocumentRequirement(
            id="paystubs",
            name="Recent Paystubs",
            description="Most recent 30 days of paystubs showing YTD earnings",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="30 days"
        ))
        
        checklist.append(DocumentRequirement(
            id="w2_forms",
            name="W-2 Forms",
            description="W-2 forms for the past 2 years",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
        
        # Bonus/Commission income
        if application_data.get('has_bonus_income') or application_data.get('has_commission_income'):
            checklist.append(DocumentRequirement(
                id="bonus_commission_history",
                name="Bonus/Commission Documentation",
                description="History of bonus or commission payments for 2 years",
                category=DocumentCategory.INCOME,
                priority=DocumentPriority.REQUIRED,
                time_period="2 years",
                notes="Must have 2-year history to use for qualification"
            ))
    
    # Self-Employed
    if employment_type == 'self_employed':
        checklist.append(DocumentRequirement(
            id="tax_returns_personal",
            name="Personal Tax Returns",
            description="Complete personal tax returns with all schedules",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
        
        checklist.append(DocumentRequirement(
            id="tax_returns_business",
            name="Business Tax Returns",
            description="Business tax returns (1120, 1120S, or 1065)",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
        
        checklist.append(DocumentRequirement(
            id="business_license",
            name="Business License",
            description="Current business license or registration",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="profit_loss_ytd",
            name="Year-to-Date Profit & Loss Statement",
            description="Current year P&L signed by borrower or prepared by CPA",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            notes="Required if more than 90 days from year-end"
        ))
        
        # Business bank statements for additional verification
        checklist.append(DocumentRequirement(
            id="business_bank_statements",
            name="Business Bank Statements",
            description="Business bank statements showing deposits",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.CONDITIONAL,
            count=3,
            time_period="3 months"
        ))
    
    # 1099 Contractors
    if employment_type == '1099_contractor':
        checklist.append(DocumentRequirement(
            id="1099_forms",
            name="1099 Forms",
            description="1099 forms for the past 2 years",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
        
        checklist.append(DocumentRequirement(
            id="tax_returns_personal",
            name="Personal Tax Returns",
            description="Complete personal tax returns with Schedule C",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
    
    # Retired
    if employment_type == 'retired':
        checklist.append(DocumentRequirement(
            id="social_security_award",
            name="Social Security Award Letter",
            description="Current Social Security benefits award letter",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED
        ))
        
        if application_data.get('has_pension'):
            checklist.append(DocumentRequirement(
                id="pension_award",
                name="Pension Award Letter",
                description="Current pension benefits documentation",
                category=DocumentCategory.INCOME,
                priority=DocumentPriority.REQUIRED
            ))
        
        if application_data.get('retirement_account_income'):
            checklist.append(DocumentRequirement(
                id="retirement_statements",
                name="Retirement Account Statements",
                description="Recent statements showing withdrawal schedule",
                category=DocumentCategory.INCOME,
                priority=DocumentPriority.REQUIRED,
                count=2,
                time_period="60 days"
            ))
    
    # Additional Income Sources
    if application_data.get('receives_alimony_child_support'):
        checklist.append(DocumentRequirement(
            id="alimony_documentation",
            name="Alimony/Child Support Documentation",
            description="Court order and proof of receipt for 6 months",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            notes="Include divorce decree and 6 months bank statements showing deposits"
        ))
    
    if application_data.get('has_rental_income'):
        checklist.append(DocumentRequirement(
            id="rental_agreements",
            name="Rental/Lease Agreements",
            description="Current signed lease agreements for rental properties",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="schedule_e",
            name="Schedule E (Rental Income)",
            description="Schedule E from tax returns for 2 years",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="2 years"
        ))
    
    # =========================================
    # ASSET DOCUMENTS
    # =========================================
    checklist.append(DocumentRequirement(
        id="bank_statements",
        name="Bank Statements",
        description="All pages of bank statements for checking/savings accounts",
        category=DocumentCategory.ASSETS,
        priority=DocumentPriority.REQUIRED,
        count=2,
        time_period="60 days",
        notes="All pages required, even if blank. No screenshots."
    ))
    
    # Investment/Retirement Accounts
    if application_data.get('has_investment_accounts') or application_data.get('investment_balance', 0) > 0:
        checklist.append(DocumentRequirement(
            id="investment_statements",
            name="Investment Account Statements",
            description="Brokerage, 401k, IRA, or other investment account statements",
            category=DocumentCategory.ASSETS,
            priority=DocumentPriority.REQUIRED,
            count=2,
            time_period="60 days"
        ))
    
    # Gift Funds
    if application_data.get('down_payment_source') == 'gift' or application_data.get('has_gift_funds'):
        checklist.append(DocumentRequirement(
            id="gift_letter",
            name="Gift Letter",
            description="Signed gift letter from donor stating no repayment required",
            category=DocumentCategory.ASSETS,
            priority=DocumentPriority.REQUIRED,
            notes="Must be signed by donor and include donor relationship"
        ))
        
        checklist.append(DocumentRequirement(
            id="gift_donor_bank_statement",
            name="Gift Donor Bank Statement",
            description="Donor's bank statement showing ability to give gift",
            category=DocumentCategory.ASSETS,
            priority=DocumentPriority.REQUIRED,
            time_period="60 days"
        ))
        
        checklist.append(DocumentRequirement(
            id="gift_transfer_documentation",
            name="Gift Transfer Documentation",
            description="Wire transfer receipt or canceled check showing gift transfer",
            category=DocumentCategory.ASSETS,
            priority=DocumentPriority.REQUIRED
        ))
    
    # Large Deposits (flagged based on bank statement review)
    checklist.append(DocumentRequirement(
        id="large_deposit_explanation",
        name="Large Deposit Documentation",
        description="Paper trail for any deposits over 50% of monthly income",
        category=DocumentCategory.ASSETS,
        priority=DocumentPriority.CONDITIONAL,
        notes="Will be requested if large deposits are identified in bank statements"
    ))
    
    # =========================================
    # PROPERTY DOCUMENTS (Purchase)
    # =========================================
    loan_purpose = application_data.get('loan_purpose', 'purchase')
    
    if loan_purpose == 'purchase':
        checklist.append(DocumentRequirement(
            id="purchase_contract",
            name="Purchase Agreement/Contract",
            description="Fully executed purchase agreement with all addenda",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED,
            notes="All pages, including any amendments"
        ))
        
        checklist.append(DocumentRequirement(
            id="earnest_money",
            name="Earnest Money Documentation",
            description="Copy of earnest money check and proof it cleared",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
    
    # =========================================
    # PROPERTY DOCUMENTS (Refinance)
    # =========================================
    if loan_purpose == 'refinance':
        checklist.append(DocumentRequirement(
            id="current_mortgage_statement",
            name="Current Mortgage Statement",
            description="Most recent mortgage statement showing payment and balance",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="homeowners_insurance_dec",
            name="Homeowner's Insurance Declaration Page",
            description="Current insurance policy declaration page",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="property_tax_bill",
            name="Property Tax Bill",
            description="Most recent property tax bill or statement",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
        
        # Second Mortgage/HELOC
        if application_data.get('has_second_mortgage') or application_data.get('has_heloc'):
            checklist.append(DocumentRequirement(
                id="second_mortgage_statement",
                name="Second Mortgage/HELOC Statement",
                description="Most recent statement for second mortgage or HELOC",
                category=DocumentCategory.PROPERTY,
                priority=DocumentPriority.REQUIRED
            ))
    
    # HOA Documents (if applicable)
    if application_data.get('has_hoa') or application_data.get('property_type') in ['condo', 'townhouse']:
        checklist.append(DocumentRequirement(
            id="hoa_statement",
            name="HOA Statement",
            description="Current HOA dues statement or coupon book",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
    
    # =========================================
    # REAL ESTATE OWNED
    # =========================================
    if application_data.get('owns_other_properties'):
        checklist.append(DocumentRequirement(
            id="reo_mortgage_statements",
            name="Mortgage Statements for Other Properties",
            description="Current mortgage statements for all owned properties",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="reo_tax_bills",
            name="Property Tax Bills for Other Properties",
            description="Property tax bills for all owned properties",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
        
        checklist.append(DocumentRequirement(
            id="reo_insurance_dec",
            name="Insurance for Other Properties",
            description="Insurance declaration pages for all owned properties",
            category=DocumentCategory.PROPERTY,
            priority=DocumentPriority.REQUIRED
        ))
    
    # =========================================
    # CREDIT/DEBT DOCUMENTS
    # =========================================
    
    # Bankruptcy
    if application_data.get('bankruptcy'):
        checklist.append(DocumentRequirement(
            id="bankruptcy_discharge",
            name="Bankruptcy Discharge Papers",
            description="Bankruptcy discharge documentation",
            category=DocumentCategory.CREDIT,
            priority=DocumentPriority.REQUIRED,
            notes="Required: Petition, Schedules, and Discharge Order"
        ))
    
    # Foreclosure
    if application_data.get('previous_home_status') in ['foreclosure', 'short_sale']:
        checklist.append(DocumentRequirement(
            id="foreclosure_documentation",
            name="Foreclosure/Short Sale Documentation",
            description="Documentation of prior foreclosure or short sale",
            category=DocumentCategory.CREDIT,
            priority=DocumentPriority.REQUIRED
        ))
    
    # IRS Payment Plan
    if application_data.get('irs_debt') == 'payment_plan':
        checklist.append(DocumentRequirement(
            id="irs_payment_plan",
            name="IRS Payment Plan Agreement",
            description="IRS installment agreement and proof of payments",
            category=DocumentCategory.CREDIT,
            priority=DocumentPriority.REQUIRED,
            notes="Include last 12 months of payment history"
        ))
    
    # Child Support/Alimony Paid
    if application_data.get('pays_alimony_child_support'):
        checklist.append(DocumentRequirement(
            id="alimony_child_support_order",
            name="Court Order for Support Payments",
            description="Divorce decree or court order showing payment obligation",
            category=DocumentCategory.CREDIT,
            priority=DocumentPriority.REQUIRED
        ))
    
    # =========================================
    # LOAN-SPECIFIC DOCUMENTS
    # =========================================
    loan_type = application_data.get('loan_type', 'conventional')
    
    # VA Loans
    if loan_type == 'va':
        checklist.append(DocumentRequirement(
            id="dd214",
            name="DD-214 (Certificate of Release)",
            description="DD-214 showing honorable discharge",
            category=DocumentCategory.OTHER,
            priority=DocumentPriority.REQUIRED,
            notes="Member 4 copy preferred"
        ))
        
        checklist.append(DocumentRequirement(
            id="coe",
            name="Certificate of Eligibility (COE)",
            description="VA Certificate of Eligibility",
            category=DocumentCategory.OTHER,
            priority=DocumentPriority.REQUIRED,
            notes="We can order this for you if needed"
        ))
    
    # FHA Loans - Additional requirements typically handled at processing
    
    # USDA Loans
    if loan_type == 'usda':
        checklist.append(DocumentRequirement(
            id="usda_income_docs",
            name="Household Income Documentation",
            description="Income documentation for ALL household members 18+",
            category=DocumentCategory.INCOME,
            priority=DocumentPriority.REQUIRED,
            notes="USDA requires income verification for entire household"
        ))
    
    return checklist


def format_checklist_for_display(checklist: List[DocumentRequirement]) -> Dict:
    """
    Format checklist for frontend display, grouped by category.
    """
    grouped = {}
    
    for doc in checklist:
        category = doc.category.value
        if category not in grouped:
            grouped[category] = []
        
        grouped[category].append({
            "id": doc.id,
            "name": doc.name,
            "description": doc.description,
            "priority": doc.priority.value,
            "count": doc.count,
            "timePeriod": doc.time_period,
            "notes": doc.notes
        })
    
    # Order categories
    category_order = ["identity", "income", "assets", "property", "credit", "other"]
    category_labels = {
        "identity": "Identification",
        "income": "Income Verification",
        "assets": "Asset Documentation",
        "property": "Property Documents",
        "credit": "Credit & Debt",
        "other": "Additional Documents"
    }
    
    result = {
        "categories": [],
        "totalDocuments": len(checklist),
        "requiredCount": len([d for d in checklist if d.priority == DocumentPriority.REQUIRED])
    }
    
    for cat in category_order:
        if cat in grouped:
            result["categories"].append({
                "id": cat,
                "label": category_labels.get(cat, cat.title()),
                "documents": grouped[cat]
            })
    
    return result
```

### API Endpoint for Document Checklist

```python
# backend/routes/document_routes.py

from fastapi import APIRouter, Depends
from services.document_checklist_service import (
    generate_document_checklist,
    format_checklist_for_display
)

router = APIRouter()

@router.post("/api/documents/checklist")
async def get_document_checklist(application_data: dict):
    """
    Generate document checklist based on application data.
    
    Request Body:
    {
        "employment_type": "employed",
        "has_bonus_income": true,
        "loan_purpose": "purchase",
        "property_type": "single_family",
        "has_hoa": false,
        "down_payment_source": "savings",
        ...
    }
    """
    checklist = generate_document_checklist(application_data)
    formatted = format_checklist_for_display(checklist)
    
    return {
        "status": "success",
        "checklist": formatted
    }


@router.get("/api/documents/checklist/{application_id}")
async def get_saved_checklist(application_id: str):
    """
    Get previously generated checklist for an application.
    """
    # Retrieve from database
    application = await db.applications.find_one({"_id": application_id})
    
    if not application:
        raise HTTPException(404, "Application not found")
    
    # Regenerate checklist from saved application data
    checklist = generate_document_checklist(application.get("answers", {}))
    formatted = format_checklist_for_display(checklist)
    
    # Merge with upload status
    uploaded_docs = await db.documents.find({"application_id": application_id}).to_list(None)
    uploaded_ids = {doc["document_type"] for doc in uploaded_docs}
    
    for category in formatted["categories"]:
        for doc in category["documents"]:
            doc["uploaded"] = doc["id"] in uploaded_ids
    
    return {
        "status": "success",
        "checklist": formatted,
        "uploadedCount": len(uploaded_ids)
    }
```

### React Component - Document Checklist Display

```jsx
// frontend/src/components/DocumentChecklist.js

import React, { useState, useEffect } from 'react';
import './DocumentChecklist.css';

const DocumentChecklist = ({ applicationData, applicationId, onUpload }) => {
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedCategories, setExpandedCategories] = useState({});

  useEffect(() => {
    fetchChecklist();
  }, [applicationData, applicationId]);

  const fetchChecklist = async () => {
    try {
      setLoading(true);
      
      const endpoint = applicationId 
        ? `/api/documents/checklist/${applicationId}`
        : '/api/documents/checklist';
      
      const response = await fetch(endpoint, {
        method: applicationId ? 'GET' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: applicationId ? undefined : JSON.stringify(applicationData)
      });
      
      const data = await response.json();
      setChecklist(data.checklist);
      
      // Expand all categories by default
      const expanded = {};
      data.checklist.categories.forEach(cat => {
        expanded[cat.id] = true;
      });
      setExpandedCategories(expanded);
      
    } catch (error) {
      console.error('Failed to fetch checklist:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (categoryId) => {
    setExpandedCategories(prev => ({
      ...prev,
      [categoryId]: !prev[categoryId]
    }));
  };

  const handleFileUpload = async (documentId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('documentType', documentId);
    formData.append('applicationId', applicationId);
    
    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        // Refresh checklist to show uploaded status
        fetchChecklist();
        onUpload?.(documentId);
      }
    } catch (error) {
      console.error('Upload failed:', error);
    }
  };

  if (loading) {
    return <div className="checklist-loading">Loading document checklist...</div>;
  }

  if (!checklist) {
    return <div className="checklist-error">Unable to load document checklist</div>;
  }

  return (
    <div className="document-checklist">
      <div className="checklist-header">
        <h2>Required Documents</h2>
        <p className="checklist-summary">
          {checklist.requiredCount} required documents
        </p>
      </div>

      {checklist.categories.map(category => (
        <div key={category.id} className="checklist-category">
          <button 
            className="category-header"
            onClick={() => toggleCategory(category.id)}
          >
            <span className="category-label">{category.label}</span>
            <span className="category-count">
              {category.documents.filter(d => d.uploaded).length} / {category.documents.length}
            </span>
            <span className={`expand-icon ${expandedCategories[category.id] ? 'expanded' : ''}`}>
              ▼
            </span>
          </button>

          {expandedCategories[category.id] && (
            <div className="category-documents">
              {category.documents.map(doc => (
                <div 
                  key={doc.id} 
                  className={`document-item ${doc.uploaded ? 'uploaded' : ''} ${doc.priority}`}
                >
                  <div className="document-info">
                    <div className="document-header">
                      <span className={`status-indicator ${doc.uploaded ? 'complete' : 'pending'}`} />
                      <h4>{doc.name}</h4>
                      {doc.priority === 'required' && (
                        <span className="required-badge">Required</span>
                      )}
                    </div>
                    <p className="document-description">{doc.description}</p>
                    
                    {doc.timePeriod && (
                      <p className="document-meta">
                        <strong>Time Period:</strong> {doc.timePeriod}
                      </p>
                    )}
                    {doc.count > 1 && (
                      <p className="document-meta">
                        <strong>Quantity:</strong> {doc.count} documents needed
                      </p>
                    )}
                    {doc.notes && (
                      <p className="document-notes">{doc.notes}</p>
                    )}
                  </div>

                  <div className="document-actions">
                    {doc.uploaded ? (
                      <div className="uploaded-indicator">
                        <span className="checkmark">✓</span>
                        <span>Uploaded</span>
                      </div>
                    ) : (
                      <label className="upload-button">
                        <input
                          type="file"
                          accept=".pdf,.jpg,.jpeg,.png"
                          onChange={(e) => handleFileUpload(doc.id, e.target.files[0])}
                          hidden
                        />
                        Upload
                      </label>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default DocumentChecklist;
```

---

## 8. Technical Utilities

### Auto-Save Hook

```javascript
// frontend/src/hooks/useAutoSave.js

import { useEffect, useRef, useCallback } from 'react';
import debounce from 'lodash/debounce';

export const useAutoSave = (data, saveFunction, options = {}) => {
  const {
    delay = 2000,           // Debounce delay in ms
    enabled = true,          // Enable/disable auto-save
    onSaveStart = () => {},  // Callback when save starts
    onSaveSuccess = () => {}, // Callback on successful save
    onSaveError = () => {}   // Callback on save error
  } = options;

  const previousData = useRef(data);
  const isMounted = useRef(true);

  // Debounced save function
  const debouncedSave = useCallback(
    debounce(async (dataToSave) => {
      if (!isMounted.current) return;
      
      try {
        onSaveStart();
        await saveFunction(dataToSave);
        onSaveSuccess();
      } catch (error) {
        onSaveError(error);
      }
    }, delay),
    [saveFunction, delay, onSaveStart, onSaveSuccess, onSaveError]
  );

  useEffect(() => {
    if (!enabled) return;

    // Only save if data has changed
    const hasChanged = JSON.stringify(data) !== JSON.stringify(previousData.current);
    
    if (hasChanged) {
      previousData.current = data;
      debouncedSave(data);
    }

    return () => {
      debouncedSave.cancel();
    };
  }, [data, enabled, debouncedSave]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMounted.current = false;
      debouncedSave.cancel();
    };
  }, [debouncedSave]);

  // Force save (bypass debounce)
  const forceSave = useCallback(async () => {
    debouncedSave.cancel();
    try {
      onSaveStart();
      await saveFunction(data);
      onSaveSuccess();
    } catch (error) {
      onSaveError(error);
    }
  }, [data, saveFunction, debouncedSave, onSaveStart, onSaveSuccess, onSaveError]);

  return { forceSave };
};

// Usage Example:
// const { forceSave } = useAutoSave(formData, saveToServer, {
//   delay: 3000,
//   onSaveStart: () => setIsSaving(true),
//   onSaveSuccess: () => { setIsSaving(false); setLastSaved(new Date()); },
//   onSaveError: (err) => { setIsSaving(false); setError(err); }
// });
```

### Input Formatters

```javascript
// frontend/src/utils/formatters.js

/**
 * Format phone number as (XXX) XXX-XXXX
 */
export const formatPhoneNumber = (value) => {
  if (!value) return '';
  
  // Remove all non-digits
  const digits = value.replace(/\D/g, '');
  
  // Limit to 10 digits
  const trimmed = digits.slice(0, 10);
  
  // Format based on length
  if (trimmed.length === 0) return '';
  if (trimmed.length <= 3) return `(${trimmed}`;
  if (trimmed.length <= 6) return `(${trimmed.slice(0, 3)}) ${trimmed.slice(3)}`;
  return `(${trimmed.slice(0, 3)}) ${trimmed.slice(3, 6)}-${trimmed.slice(6)}`;
};

/**
 * Format SSN as XXX-XX-XXXX
 */
export const formatSSN = (value) => {
  if (!value) return '';
  
  const digits = value.replace(/\D/g, '');
  const trimmed = digits.slice(0, 9);
  
  if (trimmed.length === 0) return '';
  if (trimmed.length <= 3) return trimmed;
  if (trimmed.length <= 5) return `${trimmed.slice(0, 3)}-${trimmed.slice(3)}`;
  return `${trimmed.slice(0, 3)}-${trimmed.slice(3, 5)}-${trimmed.slice(5)}`;
};

/**
 * Format currency with commas and 2 decimal places
 */
export const formatCurrency = (value, options = {}) => {
  const {
    includeSymbol = true,
    decimals = 0,
    allowNegative = false
  } = options;
  
  if (value === '' || value === null || value === undefined) return '';
  
  // Remove all non-numeric characters except decimal and minus
  let cleaned = value.toString().replace(/[^\d.-]/g, '');
  
  // Handle negative
  const isNegative = cleaned.startsWith('-');
  if (!allowNegative) {
    cleaned = cleaned.replace(/-/g, '');
  } else {
    cleaned = cleaned.replace(/-/g, '');
  }
  
  // Parse to number
  let number = parseFloat(cleaned) || 0;
  if (isNegative && allowNegative) number = -number;
  
  // Format with commas
  const formatted = number.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
  
  return includeSymbol ? `$${formatted}` : formatted;
};

/**
 * Parse formatted currency back to number
 */
export const parseCurrency = (value) => {
  if (!value) return 0;
  const cleaned = value.toString().replace(/[^\d.-]/g, '');
  return parseFloat(cleaned) || 0;
};

/**
 * Format percentage
 */
export const formatPercentage = (value, decimals = 3) => {
  if (value === '' || value === null || value === undefined) return '';
  
  const digits = value.toString().replace(/[^\d.]/g, '');
  const number = parseFloat(digits);
  
  if (isNaN(number)) return '';
  if (number > 100) return '100';
  
  return number.toFixed(decimals).replace(/\.?0+$/, '');
};

/**
 * Format date as MM/DD/YYYY
 */
export const formatDate = (value) => {
  if (!value) return '';
  
  const digits = value.replace(/\D/g, '');
  const trimmed = digits.slice(0, 8);
  
  if (trimmed.length === 0) return '';
  if (trimmed.length <= 2) return trimmed;
  if (trimmed.length <= 4) return `${trimmed.slice(0, 2)}/${trimmed.slice(2)}`;
  return `${trimmed.slice(0, 2)}/${trimmed.slice(2, 4)}/${trimmed.slice(4)}`;
};

/**
 * Format ZIP code (5 or 9 digits)
 */
export const formatZipCode = (value) => {
  if (!value) return '';
  
  const digits = value.replace(/\D/g, '');
  const trimmed = digits.slice(0, 9);
  
  if (trimmed.length <= 5) return trimmed;
  return `${trimmed.slice(0, 5)}-${trimmed.slice(5)}`;
};

/**
 * Format EIN as XX-XXXXXXX
 */
export const formatEIN = (value) => {
  if (!value) return '';
  
  const digits = value.replace(/\D/g, '');
  const trimmed = digits.slice(0, 9);
  
  if (trimmed.length <= 2) return trimmed;
  return `${trimmed.slice(0, 2)}-${trimmed.slice(2)}`;
};
```

### Validation Utilities

```javascript
// frontend/src/utils/validation.js

/**
 * Email validation
 */
export const isValidEmail = (email) => {
  if (!email) return false;
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
};

/**
 * Phone number validation (10 digits)
 */
export const isValidPhone = (phone) => {
  if (!phone) return false;
  const digits = phone.replace(/\D/g, '');
  return digits.length === 10;
};

/**
 * SSN validation (9 digits, basic format check)
 */
export const isValidSSN = (ssn) => {
  if (!ssn) return false;
  const digits = ssn.replace(/\D/g, '');
  
  // Must be 9 digits
  if (digits.length !== 9) return false;
  
  // Cannot start with 9 (ITIN) or 000
  if (digits.startsWith('9') || digits.startsWith('000')) return false;
  
  // Cannot have 00 in positions 4-5 or 0000 in positions 6-9
  if (digits.slice(3, 5) === '00' || digits.slice(5) === '0000') return false;
  
  return true;
};

/**
 * ZIP code validation
 */
export const isValidZipCode = (zip) => {
  if (!zip) return false;
  const digits = zip.replace(/\D/g, '');
  return digits.length === 5 || digits.length === 9;
};

/**
 * Date validation (MM/DD/YYYY)
 */
export const isValidDate = (dateString) => {
  if (!dateString) return false;
  
  const parts = dateString.split('/');
  if (parts.length !== 3) return false;
  
  const month = parseInt(parts[0], 10);
  const day = parseInt(parts[1], 10);
  const year = parseInt(parts[2], 10);
  
  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  if (year < 1900 || year > 2100) return false;
  
  // Check for valid day in month
  const date = new Date(year, month - 1, day);
  return date.getMonth() === month - 1 && date.getDate() === day;
};

/**
 * Date of birth validation (must be at least 18 years old)
 */
export const isValidDOB = (dateString, minAge = 18) => {
  if (!isValidDate(dateString)) return false;
  
  const parts = dateString.split('/');
  const dob = new Date(
    parseInt(parts[2], 10),
    parseInt(parts[0], 10) - 1,
    parseInt(parts[1], 10)
  );
  
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const monthDiff = today.getMonth() - dob.getMonth();
  
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
    age--;
  }
  
  return age >= minAge;
};

/**
 * Currency amount validation
 */
export const isValidCurrency = (value, options = {}) => {
  const { min = 0, max = Infinity, required = true } = options;
  
  if (!value && value !== 0) return !required;
  
  const number = typeof value === 'string' 
    ? parseFloat(value.replace(/[^\d.-]/g, ''))
    : value;
  
  if (isNaN(number)) return false;
  return number >= min && number <= max;
};

/**
 * Percentage validation
 */
export const isValidPercentage = (value, options = {}) => {
  const { min = 0, max = 100, required = true } = options;
  
  if (!value && value !== 0) return !required;
  
  const number = parseFloat(value);
  if (isNaN(number)) return false;
  
  return number >= min && number <= max;
};

/**
 * Create validation schema for a question
 */
export const createValidator = (question) => {
  const validators = [];
  
  // Required check
  if (question.required !== false) {
    validators.push({
      test: (value) => {
        if (value === null || value === undefined || value === '') return false;
        if (Array.isArray(value)) return value.length > 0;
        return true;
      },
      message: 'This field is required'
    });
  }
  
  // Type-specific validation
  switch (question.type) {
    case 'email':
      validators.push({
        test: isValidEmail,
        message: 'Please enter a valid email address'
      });
      break;
      
    case 'phone':
      validators.push({
        test: isValidPhone,
        message: 'Please enter a valid 10-digit phone number'
      });
      break;
      
    case 'ssn':
      validators.push({
        test: isValidSSN,
        message: 'Please enter a valid Social Security Number'
      });
      break;
      
    case 'date':
      validators.push({
        test: isValidDate,
        message: 'Please enter a valid date (MM/DD/YYYY)'
      });
      break;
      
    case 'dob':
      validators.push({
        test: (v) => isValidDOB(v, 18),
        message: 'You must be at least 18 years old'
      });
      break;
      
    case 'zip':
      validators.push({
        test: isValidZipCode,
        message: 'Please enter a valid ZIP code'
      });
      break;
      
    case 'currency':
      validators.push({
        test: (v) => isValidCurrency(v, question.validation),
        message: question.validation?.message || 'Please enter a valid amount'
      });
      break;
      
    case 'percentage':
      validators.push({
        test: (v) => isValidPercentage(v, question.validation),
        message: 'Please enter a valid percentage (0-100)'
      });
      break;
  }
  
  // Custom validation
  if (question.validate) {
    validators.push({
      test: question.validate,
      message: question.validationMessage || 'Invalid value'
    });
  }
  
  return (value) => {
    for (const validator of validators) {
      if (!validator.test(value)) {
        return validator.message;
      }
    }
    return null; // Valid
  };
};
```

### Progress Calculation Utility

```javascript
// frontend/src/utils/progressCalculator.js

/**
 * Calculate application progress based on completed questions
 */
export const calculateProgress = (stages, answers, currentStage, currentQuestionIndex) => {
  // Filter to only visible stages (exclude hidden stages like 'account')
  const visibleStages = stages.filter(stage => !stage.hideFromProgress);
  
  const currentStageIndex = visibleStages.findIndex(s => s.id === currentStage);
  
  // If current stage is hidden, return 0
  if (currentStageIndex === -1) return 0;
  
  // Calculate base progress from completed stages
  const stageProgress = (currentStageIndex / visibleStages.length) * 100;
  
  // Get questions for current stage
  const currentStageData = visibleStages[currentStageIndex];
  if (!currentStageData || !currentStageData.questions) {
    return Math.round(stageProgress);
  }
  
  // Filter to enabled questions based on conditional logic
  const enabledQuestions = currentStageData.questions.filter(q => {
    if (!q.showIf) return true;
    return evaluateCondition(q.showIf, answers);
  });
  
  if (enabledQuestions.length === 0) {
    return Math.round(stageProgress);
  }
  
  // Add progress within current stage
  const questionProgress = (currentQuestionIndex / enabledQuestions.length) * (100 / visibleStages.length);
  
  return Math.round(stageProgress + questionProgress);
};

/**
 * Evaluate conditional display logic
 */
export const evaluateCondition = (condition, answers) => {
  if (!condition) return true;
  
  // Handle array conditions (OR logic)
  if (Array.isArray(condition)) {
    return condition.some(c => evaluateCondition(c, answers));
  }
  
  // Handle object conditions (AND logic for multiple keys)
  return Object.entries(condition).every(([key, expected]) => {
    const actual = answers[key];
    
    // Array of acceptable values (OR)
    if (Array.isArray(expected)) {
      return expected.includes(actual);
    }
    
    // Boolean check
    if (typeof expected === 'boolean') {
      return actual === expected;
    }
    
    // Exact match
    return actual === expected;
  });
};

/**
 * Get next enabled question
 */
export const getNextQuestion = (questions, currentIndex, answers) => {
  for (let i = currentIndex + 1; i < questions.length; i++) {
    const question = questions[i];
    if (!question.showIf || evaluateCondition(question.showIf, answers)) {
      return { question, index: i };
    }
  }
  return null;
};

/**
 * Get previous enabled question
 */
export const getPreviousQuestion = (questions, currentIndex, answers) => {
  for (let i = currentIndex - 1; i >= 0; i--) {
    const question = questions[i];
    if (!question.showIf || evaluateCondition(question.showIf, answers)) {
      return { question, index: i };
    }
  }
  return null;
};

/**
 * Get all enabled questions for a stage
 */
export const getEnabledQuestions = (questions, answers) => {
  return questions.filter(q => {
    if (!q.showIf) return true;
    return evaluateCondition(q.showIf, answers);
  });
};

/**
 * Calculate completion status for each stage
 */
export const getStageCompletionStatus = (stages, answers) => {
  return stages.map(stage => {
    if (!stage.questions || stage.questions.length === 0) {
      return { ...stage, completion: 0, isComplete: false };
    }
    
    const enabledQuestions = getEnabledQuestions(stage.questions, answers);
    const answeredCount = enabledQuestions.filter(q => {
      const answer = answers[q.id];
      return answer !== null && answer !== undefined && answer !== '';
    }).length;
    
    const completion = enabledQuestions.length > 0 
      ? Math.round((answeredCount / enabledQuestions.length) * 100)
      : 0;
    
    return {
      ...stage,
      completion,
      isComplete: completion === 100,
      totalQuestions: enabledQuestions.length,
      answeredQuestions: answeredCount
    };
  });
};
```

---

## 9. Implementation Checklist

Use this checklist to track implementation progress:

### Phase 1: Core Application Flow
- [ ] Application entry point component with routing
- [ ] Purchase application stages 1-4 (Declarations through Income)
- [ ] Progress bar component with stage indicators
- [ ] Auto-save functionality
- [ ] Basic input formatters

### Phase 2: Complete Purchase Application
- [ ] Purchase application stages 5-9 (Assets through Real Estate Agents)
- [ ] Conditional question logic (showIf)
- [ ] All input types (boolean, single-choice, multi-input, currency, etc.)
- [ ] Validation for all question types

### Phase 3: Refinance Application
- [ ] Refinance-specific stages
- [ ] Current mortgage information capture
- [ ] Second mortgage/HELOC handling
- [ ] Mortgage statement upload & parsing

### Phase 4: Integrations
- [ ] Google Places API for employer autocomplete
- [ ] Google Places API for address autocomplete
- [ ] CRM realtor lookup integration
- [ ] Claude Vision API for document parsing

### Phase 5: Database & Backend
- [ ] PostgreSQL schema implementation
- [ ] API endpoints for application CRUD
- [ ] Document upload endpoints
- [ ] Checklist generation endpoint

### Phase 6: Document Management
- [ ] Dynamic document checklist generator
- [ ] Document upload UI
- [ ] Document status tracking
- [ ] Document categorization

### Phase 7: Testing & Polish
- [ ] Unit tests for formatters and validators
- [ ] Integration tests for API endpoints
- [ ] End-to-end testing of application flow
- [ ] Mobile responsiveness
- [ ] Accessibility audit

---

## 10. Notes for Developer

1. **Progressive Disclosure**: The application uses a one-question-at-a-time approach for better UX. Each question should animate in/out smoothly.

2. **Conditional Logic**: Many questions only appear based on previous answers. Always check `showIf` conditions before rendering.

3. **Auto-Save**: Implement debounced auto-save to prevent data loss. Save after 2-3 seconds of inactivity.

4. **API Keys**: Store all API keys (Google Places, Anthropic) in environment variables. Never commit keys to source control.

5. **Error Handling**: Provide clear error messages for API failures. Allow users to retry or continue without autocomplete.

6. **Mobile First**: Design for mobile screens first, then enhance for desktop. The majority of users will be on mobile.

7. **Accessibility**: Ensure keyboard navigation works throughout. Use proper ARIA labels and roles.

8. **Performance**: Lazy load stages that aren't immediately needed. Use code splitting for large components.

9. **Security**: Sanitize all user inputs. Use parameterized queries for database operations. Validate on both client and server.

10. **Testing**: Write tests for conditional logic, formatters, and validators first. These are the most error-prone areas.

---

**Document Version**: 1.0  
**Last Updated**: January 2025  
**Author**: AI Assistant  
**Status**: Complete Specification
