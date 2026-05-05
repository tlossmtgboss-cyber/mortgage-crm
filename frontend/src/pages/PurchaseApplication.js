import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import PaymentCalculator from '../components/PaymentCalculator';
import './AdaptiveURLA.css';
import { toast } from '../utils/toast';

/**
 * PurchaseApplication - Streamlined Home Purchase Application
 *
 * Tailored 6-Stage Flow for Home Buyers:
 * 1. Declarations - Key questions for personalization
 * 2. Profile - Personal information
 * 3. Income - Employment and income details
 * 4. Assets - Savings and down payment funds
 * 5. Property - New home details and loan program
 * 6. Review - Summary and submit
 */

const STAGES = [
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
const VISIBLE_STAGES = STAGES.filter(s => !s.hideFromProgress);

// Generate documents needed based on user's declarations and data - DYNAMIC and PERSONALIZED
// Now includes borrower names, employer names, and specific years for all documents
const getRequiredDocuments = (
  declarations = {},
  assetData = {},
  profileData = {},
  incomeData = {},
  coBorrowerData = {},
  coBorrowerIncomeData = {}
) => {
  const docs = [];
  const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';
  const hasGiftFunds = declarations.gift_funds === 'yes';
  const hasCoBorrower = ['2', '3', '4+'].includes(declarations.borrower_count);
  const maximizesDeductions = declarations.write_off_expenses === 'yes';

  // Get borrower names for personalization (use first name or fallback)
  const borrowerFirstName = profileData?.firstName?.trim() || 'Primary Borrower';
  const coBorrowerFirstName = coBorrowerData?.firstName?.trim() || 'Co-Borrower';

  // Get employer names for personalization
  const primaryEmployer = incomeData?.employerName?.trim() || null;
  const coBorrowerEmployer = coBorrowerIncomeData?.employerName?.trim() || null;

  // Get current and prior years for document labels
  const today = new Date();
  const currentYear = today.getFullYear();
  const priorYear = currentYear - 1;
  const twoYearsAgo = currentYear - 2;

  // Parse asset values
  const hasCheckingOrSavings = (parseFloat(assetData.checking) || 0) > 0 || (parseFloat(assetData.savings) || 0) > 0;
  const hasInvestmentOrRetirement = (parseFloat(assetData.investments) || 0) > 0 || (parseFloat(assetData.retirement) || 0) > 0;

  // === IDENTITY DOCUMENTS ===
  // Only add government ID after citizenship question is answered
  if (declarations.citizenship_status) {
    docs.push({
      id: 'id',
      name: `${borrowerFirstName}'s Government ID`,
      description: "Driver's license or passport",
      category: 'identity',
      stage: 'declarations'
    });
  }

  // Citizenship-based documents
  if (declarations.citizenship_status === 'permanent_resident') {
    docs.push({
      id: 'green_card',
      name: `${borrowerFirstName}'s Green Card`,
      description: 'Unexpired Permanent Resident Card',
      category: 'identity',
      stage: 'declarations'
    });
  }
  if (declarations.citizenship_status === 'non_permanent_resident' || declarations.citizenship_status === 'non_resident') {
    docs.push({
      id: 'visa_docs',
      name: `${borrowerFirstName}'s Visa Documents`,
      description: 'Current visa and work authorization',
      category: 'identity',
      stage: 'declarations'
    });
  }

  // === INCOME DOCUMENTS ===
  const jan28 = new Date(currentYear, 0, 28); // January 28th
  const apr15 = new Date(currentYear, 3, 15); // April 15th
  const isBeforeJan28 = today < jan28;

  if (isSelfEmployed) {
    // Date-based logic for self-employment documents
    const businessName = declarations.business_name?.trim() || 'your business';

    if (maximizesDeductions) {
      // Heavy deductions - use bank statement program instead of tax returns
      docs.push({
        id: 'business_bank_statements',
        name: `${borrowerFirstName}'s Business Bank Statements`,
        description: `12 consecutive months of bank statements for ${businessName}`,
        category: 'income',
        stage: 'income'
      });
    } else {
      // Standard self-employed documentation
      if (isBeforeJan28) {
        // Before Jan 28 - prior year taxes can't be filed yet, need P&L
        docs.push({
          id: 'tax_returns',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessName} ${twoYearsAgo} business tax return`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'profit_loss',
          name: `${priorYear} Profit & Loss Statement`,
          description: `Year-to-date ${priorYear} P&L for ${businessName} (signed by ${borrowerFirstName})`,
          category: 'income',
          stage: 'income'
        });
      } else if (declarations.prior_year_taxes_filed === 'yes') {
        // After Jan 28 and taxes filed - request full tax returns
        docs.push({
          id: 'tax_returns_recent',
          name: `${borrowerFirstName}'s ${priorYear} Personal Tax Return`,
          description: `Complete ${priorYear} personal tax return (all pages & schedules)`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'tax_returns_prior',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns_recent',
          name: `${priorYear} Business Tax Return`,
          description: `${businessName} ${priorYear} business tax return`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns_prior',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessName} ${twoYearsAgo} business tax return`,
          category: 'income',
          stage: 'income'
        });
      } else {
        // After Jan 28 but taxes not filed - need prior year P&L
        docs.push({
          id: 'tax_returns',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessName} ${twoYearsAgo} business tax return`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'profit_loss',
          name: `${priorYear} Profit & Loss Statement`,
          description: `Year-to-date ${priorYear} P&L for ${businessName} (signed by ${borrowerFirstName})`,
          category: 'income',
          stage: 'income'
        });
      }
    }

    // Articles of Incorporation for S-Corp or C-Corp
    if (declarations.business_type === 's_corp' || declarations.business_type === 'c_corp') {
      docs.push({
        id: 'articles_incorporation',
        name: `${businessName} Articles of Incorporation`,
        description: 'Corporate formation documents showing ownership',
        category: 'income',
        stage: 'income'
      });
    }
  } else {
    // W-2 employee - personalized with employer name
    const employerLabel = primaryEmployer || 'your employer';
    docs.push({
      id: 'paystubs',
      name: `${borrowerFirstName}'s Pay Stubs from ${employerLabel}`,
      description: `2 consecutive recent pay stubs from ${employerLabel}`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'w2_recent',
      name: `${borrowerFirstName}'s ${priorYear} W-2 from ${employerLabel}`,
      description: `${priorYear} W-2 form from ${employerLabel}`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'w2_prior',
      name: `${borrowerFirstName}'s ${twoYearsAgo} W-2 from ${employerLabel}`,
      description: `${twoYearsAgo} W-2 form from ${employerLabel}`,
      category: 'income',
      stage: 'income'
    });
  }

  // === DIVORCE / CHILD SUPPORT DOCUMENTS ===
  if ((declarations.marital_status === 'divorced' || declarations.marital_status === 'separated') &&
      declarations.child_support_alimony && declarations.child_support_alimony !== 'neither') {
    docs.push({
      id: 'divorce_decree',
      name: `${borrowerFirstName}'s Divorce Decree`,
      description: 'Final divorce decree with property/support terms',
      category: 'income',
      stage: 'declarations'
    });
    docs.push({
      id: 'property_settlement',
      name: 'Property Settlement Agreement',
      description: 'Marital settlement agreement (if separate from decree)',
      category: 'income',
      stage: 'declarations'
    });
  }

  // === VETERAN DOCUMENTS ===
  if (declarations.veteran === 'yes' || declarations.veteran === 'active' || declarations.veteran === 'spouse') {
    docs.push({
      id: 'va_coe',
      name: `${borrowerFirstName}'s VA Certificate of Eligibility`,
      description: 'VA COE - can be obtained from eBenefits portal',
      category: 'identity',
      stage: 'declarations'
    });
  }
  if (declarations.va_disability === 'pending') {
    docs.push({
      id: 'va_pending_claim',
      name: 'VA Pending Disability Claim',
      description: 'Documentation of pending VA disability claim',
      category: 'identity',
      stage: 'declarations'
    });
  }

  // === IRS DOCUMENTS ===
  if (declarations.irs_balance_owed === 'payment_plan') {
    docs.push({
      id: 'irs_payment_arrangement',
      name: `${borrowerFirstName}'s IRS Payment Arrangement`,
      description: 'IRS installment agreement letter showing payment terms',
      category: 'income',
      stage: 'declarations'
    });
  } else if (declarations.irs_balance_owed === 'yes') {
    docs.push({
      id: 'irs_payoff',
      name: `${borrowerFirstName}'s IRS Payoff Statement`,
      description: 'Current IRS balance and payoff amount',
      category: 'income',
      stage: 'declarations'
    });
  }

  // === PREVIOUS HOME / RENTAL PROPERTY DOCUMENTS ===
  if (declarations.previous_home_mortgage === 'yes') {
    docs.push({
      id: 'existing_mortgage_statement',
      name: 'Current Mortgage Statement',
      description: 'Most recent mortgage statement for existing property',
      category: 'assets',
      stage: 'declarations'
    });
  }
  if (declarations.previous_home_status === 'renting_out') {
    docs.push({
      id: 'rental_tax_returns',
      name: `${borrowerFirstName}'s Tax Return with Schedule E`,
      description: `${priorYear} tax return showing rental income (Schedule E)`,
      category: 'income',
      stage: 'declarations'
    });
    docs.push({
      id: 'lease_agreement',
      name: 'Current Lease Agreement',
      description: 'Signed lease agreement for rental property',
      category: 'assets',
      stage: 'declarations'
    });
  }

  // === CREDIT APPLICATION DOCUMENTS ===
  if (declarations.recent_credit_applications === 'yes' && declarations.credit_application_approved === 'yes') {
    const creditType = declarations.credit_application_type;
    const creditLabels = {
      'auto_loan': 'Auto Loan Statement',
      'credit_card': 'Credit Card Statement',
      'personal_loan': 'Personal Loan Statement',
      'other': 'New Account Statement'
    };
    const label = creditLabels[creditType] || 'New Account Statement';
    docs.push({
      id: 'new_credit_statement',
      name: `${borrowerFirstName}'s ${label}`,
      description: 'Statement showing account balance and payment for recently opened account',
      category: 'assets',
      stage: 'declarations'
    });
  }

  // === BANKRUPTCY DOCUMENTS ===
  if (declarations.credit_issues === 'bankruptcy') {
    if (declarations.bankruptcy_type === 'chapter_7') {
      // Chapter 7 - only need docs if within 7 years
      if (declarations.bankruptcy_discharge_ch7 !== '8_years_or_more') {
        docs.push({
          id: 'bankruptcy_docs',
          name: `${borrowerFirstName}'s Chapter 7 Bankruptcy Discharge`,
          description: 'Chapter 7 discharge papers showing case number and discharge date',
          category: 'identity',
          stage: 'declarations'
        });
      }
    } else if (declarations.bankruptcy_type === 'chapter_13') {
      if (declarations.chapter_13_status === 'active_paying') {
        docs.push({
          id: 'ch13_payment_history',
          name: 'Chapter 13 Payment History',
          description: '12-month payment history from Chapter 13 trustee',
          category: 'identity',
          stage: 'declarations'
        });
        docs.push({
          id: 'ch13_court_approval',
          name: 'Court Approval for New Mortgage',
          description: 'Court letter approving new mortgage while in Chapter 13',
          category: 'identity',
          stage: 'declarations'
        });
      } else {
        docs.push({
          id: 'bankruptcy_discharge',
          name: `${borrowerFirstName}'s Chapter 13 Discharge`,
          description: 'Chapter 13 discharge documents',
          category: 'identity',
          stage: 'declarations'
        });
      }
    } else if (declarations.bankruptcy_type === 'chapter_12') {
      docs.push({
        id: 'ch12_payment_history',
        name: 'Chapter 12 Payment History',
        description: '12-month payment history from trustee',
        category: 'identity',
        stage: 'declarations'
      });
      docs.push({
        id: 'ch12_court_approval',
        name: 'Court Approval Letter',
        description: 'Court approval letter for new financing',
        category: 'identity',
        stage: 'declarations'
      });
    }
  }

  // === ASSET DOCUMENTS - only show based on what user entered ===
  if (hasCheckingOrSavings) {
    docs.push({
      id: 'bank_statements',
      name: `${borrowerFirstName}'s Bank Statements`,
      description: 'Last 2 complete months for all checking/savings accounts',
      category: 'assets',
      stage: 'assets'
    });
  }
  if (hasInvestmentOrRetirement) {
    docs.push({
      id: 'investment_statements',
      name: `${borrowerFirstName}'s Investment/Retirement Statements`,
      description: 'Most recent quarterly statements for investment & retirement accounts',
      category: 'assets',
      stage: 'assets'
    });
  }

  // Gift letter only if receiving gift funds
  if (hasGiftFunds) {
    docs.push({
      id: 'gift_letter',
      name: 'Gift Letter',
      description: `Signed gift letter from donor to ${borrowerFirstName}`,
      category: 'assets',
      stage: 'assets'
    });
  }

  // === CO-BORROWER DOCUMENTS ===
  if (hasCoBorrower) {
    // Co-borrower identity document
    docs.push({
      id: 'coborrower_id',
      name: `${coBorrowerFirstName}'s Government ID`,
      description: `${coBorrowerFirstName}'s driver's license or passport`,
      category: 'identity',
      stage: 'profile'
    });

    // Co-borrower income documents - personalized with their employer
    const coBorrowerEmployerLabel = coBorrowerEmployer || `${coBorrowerFirstName}'s employer`;

    docs.push({
      id: 'coborrower_paystubs',
      name: `${coBorrowerFirstName}'s Pay Stubs from ${coBorrowerEmployerLabel}`,
      description: `2 consecutive recent pay stubs from ${coBorrowerEmployerLabel}`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'coborrower_w2_recent',
      name: `${coBorrowerFirstName}'s ${priorYear} W-2 from ${coBorrowerEmployerLabel}`,
      description: `${priorYear} W-2 form from ${coBorrowerEmployerLabel}`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'coborrower_w2_prior',
      name: `${coBorrowerFirstName}'s ${twoYearsAgo} W-2 from ${coBorrowerEmployerLabel}`,
      description: `${twoYearsAgo} W-2 form from ${coBorrowerEmployerLabel}`,
      category: 'income',
      stage: 'income'
    });

    // Co-borrower bank statements if they have separate accounts
    docs.push({
      id: 'coborrower_bank_statements',
      name: `${coBorrowerFirstName}'s Bank Statements`,
      description: `Last 2 complete months for ${coBorrowerFirstName}'s accounts (if separate from ${borrowerFirstName})`,
      category: 'assets',
      stage: 'assets'
    });
  }

  return docs;
};

// Professional SVG Icon component
const Icon = ({ name, size = 24, className = '' }) => {
  const icons = {
    story: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
        <polyline points="14,2 14,8 20,8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>
      </svg>
    ),
    profile: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
      </svg>
    ),
    income: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
      </svg>
    ),
    assets: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
    home: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/>
      </svg>
    ),
    review: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/>
      </svg>
    ),
    goals: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
      </svg>
    ),
    calendar: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
    ),
    check: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20,6 9,17 4,12"/>
      </svg>
    ),
    user: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
      </svg>
    ),
    users: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
    family: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="7" r="3"/><circle cx="17" cy="7" r="2"/><path d="M13 21v-4a4 4 0 0 0-8 0v4"/><path d="M21 21v-3a3 3 0 0 0-4-2.83"/>
      </svg>
    ),
    star: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
      </svg>
    ),
    celebration: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v4m-6 2L4 6m16 2 2-2M4 16l-2 2m18-2 2 2"/><circle cx="12" cy="12" r="6"/>
      </svg>
    ),
    heart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
    ),
    document: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14,2 14,8 20,8"/>
      </svg>
    ),
    medal: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="14" r="6"/><path d="M9 6.8V2h6v4.8M12 2v6"/><path d="M15.5 8 18 2M8.5 8 6 2"/>
      </svg>
    ),
    shield: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
    ),
    globe: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
      </svg>
    ),
    briefcase: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
      </svg>
    ),
    building: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="9" y1="6" x2="9" y2="6"/><line x1="15" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="9" y2="10"/><line x1="15" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="9" y2="14"/><line x1="15" y1="14" x2="15" y2="14"/><path d="M9 22V18h6v4"/>
      </svg>
    ),
    tie: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2l3 4-3 2-3-2 3-4z"/><path d="M9 8l-2 14 5-4 5 4-2-14"/>
      </svg>
    ),
    trendDown: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,18 13.5,8.5 8.5,13.5 1,6"/><polyline points="17,18 23,18 23,12"/>
      </svg>
    ),
    balance: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v18"/><path d="M5 6l7-3 7 3"/><path d="M2 12l3-6 3 6"/><path d="M16 12l3-6 3 6"/><path d="M2 12a3 3 0 0 0 6 0M16 12a3 3 0 0 0 6 0"/>
      </svg>
    ),
    trendUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/><polyline points="17,6 23,6 23,12"/>
      </svg>
    ),
    alertTriangle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    clipboard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
      </svg>
    ),
    creditCard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
      </svg>
    ),
    gift: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20,12 20,22 4,22 4,12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>
      </svg>
    ),
    helpCircle: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    dollarSign: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
    search: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
    arrowRight: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
      </svg>
    ),
    edit: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
    ),
    thumbsUp: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
      </svg>
    ),
    barChart: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>
      </svg>
    ),
    beach: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="5"/><path d="M3 21h18"/><path d="M12 13v8"/>
      </svg>
    ),
    award: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="7"/><polyline points="8.21,13.89 7,23 12,20 17,23 15.79,13.88"/>
      </svg>
    ),
    bank: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 21h18"/><path d="M3 10h18"/><path d="M5 6l7-3 7 3"/><path d="M4 10v11"/><path d="M20 10v11"/><path d="M8 14v3"/><path d="M12 14v3"/><path d="M16 14v3"/>
      </svg>
    ),
    lock: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    ),
    refresh: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
      </svg>
    ),
    target: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
      </svg>
    ),
    bolt: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13,2 3,14 12,14 11,22 21,10 12,10"/>
      </svg>
    ),
    homeEquity: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v4"/><path d="M9 13h6"/>
      </svg>
    ),
    predictable: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="10"/><line x1="6" y1="20" x2="6" y2="10"/>
      </svg>
    ),
    netWorth: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
      </svg>
    ),
    largerHome: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M15 3l4 3"/><path d="M19 6v3"/>
      </svg>
    ),
    freedom: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/>
      </svg>
    ),
    scissors: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>
      </svg>
    ),
    retirement: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>
      </svg>
    ),
    graduation: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 2 2 3 6 3s6-1 6-3v-5"/>
      </svg>
    ),
    rocket: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
      </svg>
    ),
    calculator: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="8" y2="10"/><line x1="12" y1="10" x2="12" y2="10"/><line x1="16" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="8" y2="14"/><line x1="12" y1="14" x2="12" y2="14"/><line x1="16" y1="14" x2="16" y2="14"/><line x1="8" y1="18" x2="8" y2="18"/><line x1="12" y1="18" x2="12" y2="18"/><line x1="16" y1="18" x2="16" y2="18"/>
      </svg>
    ),
    fileText: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
    ),
    clock: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>
      </svg>
    ),
    mapPin: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
      </svg>
    ),
    x: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    ),
    info: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>
    ),
    play: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="5,3 19,12 5,21"/>
      </svg>
    ),
    car: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/>
        <circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>
      </svg>
    ),
    search: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
    refresh: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
      </svg>
    ),
    save: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17,21 17,13 7,13 7,21"/><polyline points="7,3 7,8 15,8"/>
      </svg>
    ),
  };

  return (
    <span className={`icon ${className}`} style={{ width: size, height: size, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      {icons[name] || icons.document}
    </span>
  );
};

// Purchase-specific declaration questions
const DECLARATION_QUESTIONS = [
  {
    id: 'borrower_count',
    question: 'How many people will be on this loan application?',
    type: 'choice',
    options: [
      { value: '1', label: 'Just me', icon: 'user' },
      { value: '2', label: 'Two of us', icon: 'users' },
      { value: '3', label: 'Three people', icon: 'family' },
      { value: '4+', label: 'Four or more', icon: 'family' },
    ],
    hint: 'This helps us know how many borrowers to include in the application.',
  },
  {
    id: 'co_borrower_relationship',
    question: 'What is your relationship to the other borrower(s)?',
    type: 'choice',
    options: [
      { value: 'spouse', label: 'Spouse/Partner', icon: 'heart' },
      { value: 'relative', label: 'Family member', icon: 'family' },
      { value: 'friend', label: 'Friend/Non-relative', icon: 'users' },
      { value: 'business_partner', label: 'Business partner', icon: 'briefcase' },
    ],
    hint: 'This helps us understand the borrower structure.',
    showIf: { field: 'borrower_count', values: ['2', '3', '4+'] },
  },
  {
    id: 'citizenship_status',
    question: 'What is your citizenship status?',
    type: 'choice',
    options: [
      { value: 'us_citizen', label: 'U.S. Citizen', icon: 'check' },
      { value: 'permanent_resident', label: 'Permanent Resident (Green Card)', icon: 'document' },
      { value: 'non_permanent_resident', label: 'Non-Permanent Resident (Visa)', icon: 'globe' },
      { value: 'non_resident', label: 'Non-Resident Alien', icon: 'globe' },
    ],
    hint: 'This helps determine which loan programs you qualify for.',
  },
  {
    id: 'first_time_buyer',
    question: 'Is this your first home purchase?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, first-time buyer!', icon: 'celebration' },
      { value: 'no', label: 'No, I\'ve bought before', icon: 'home' },
    ],
    hint: 'First-time buyers may qualify for special programs!',
  },
  {
    id: 'desired_state',
    question: 'What state are you looking to buy in?',
    type: 'state_select',
    hint: 'This helps us find state-specific programs and lenders.',
  },
  {
    id: 'desired_city',
    question: 'What city or area are you looking to buy in?',
    type: 'text',
    placeholder: 'e.g., Austin, Denver metro, Orange County',
    hint: 'This helps us connect you with local experts.',
  },
  {
    id: 'previous_home_status',
    question: 'What happened to your previous home?',
    type: 'choice',
    options: [
      { value: 'sold', label: 'Sold it', icon: 'check' },
      { value: 'second_home', label: 'Keeping as second home', icon: 'home' },
      { value: 'renting_out', label: 'Renting it out', icon: 'dollarSign' },
      { value: 'foreclosure', label: 'Lost to foreclosure/short sale', icon: 'alertTriangle' },
    ],
    hint: 'This affects your loan options and what we need to document.',
    showIf: { field: 'first_time_buyer', values: ['no'] },
  },
  {
    id: 'previous_home_mortgage',
    question: 'Is there a mortgage on this property?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, there is a mortgage', icon: 'document' },
      { value: 'no', label: 'No, owned free and clear', icon: 'check' },
    ],
    hint: 'We\'ll need the current mortgage statement if there is one.',
    showIf: { field: 'previous_home_status', values: ['second_home', 'renting_out'] },
  },
  {
    id: 'foreclosure_timeline',
    question: 'When did the foreclosure or short sale occur?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'clock' },
      { value: '4_to_7_years', label: '4-7 years ago', icon: 'calendar' },
      { value: 'more_than_7_years', label: 'More than 7 years ago', icon: 'calendar' },
    ],
    hint: 'Different loan programs have different waiting periods after foreclosure.',
    showIf: { field: 'previous_home_status', values: ['foreclosure'] },
  },
  {
    id: 'rental_income_previous',
    question: 'How much rental income do you receive monthly from the property?',
    type: 'currency',
    placeholder: 'Monthly rental income',
    hint: 'This rental income can help qualify you for more home.',
    showIf: { field: 'previous_home_status', values: ['renting_out'] },
  },
  {
    id: 'marital_status',
    question: 'Are you married?',
    type: 'choice',
    options: [
      { value: 'married', label: 'Yes, married', icon: 'heart' },
      { value: 'single', label: 'Single', icon: 'user' },
      { value: 'divorced', label: 'Divorced', icon: 'document' },
      { value: 'separated', label: 'Separated', icon: 'users' },
      { value: 'widowed', label: 'Widowed', icon: 'heart' },
    ],
    unlocks: ['spouse_section'],
    hideIf: { field: 'co_borrower_relationship', values: ['spouse'] }, // Skip if already indicated spouse/partner
  },
  {
    id: 'spouse_on_loan',
    question: 'Will your spouse be on the loan application?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, both of us', icon: 'users' },
      { value: 'no', label: 'No, just me', icon: 'user' },
    ],
    hint: 'In community property states, spouse income/debts may still be considered.',
    showIf: { field: 'marital_status', values: ['married'] },
  },
  {
    id: 'divorce_finalized',
    question: 'Is your divorce finalized?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, finalized', icon: 'check' },
      { value: 'pending', label: 'Still pending', icon: 'clock' },
    ],
    hint: 'A pending divorce may require additional documentation.',
    showIf: { field: 'marital_status', values: ['divorced', 'separated'] },
  },
  {
    id: 'child_support_alimony',
    question: 'Do you receive or pay child support or alimony?',
    type: 'choice',
    options: [
      { value: 'receive', label: 'I receive payments', icon: 'dollarSign' },
      { value: 'pay', label: 'I make payments', icon: 'creditCard' },
      { value: 'both', label: 'Both receive and pay', icon: 'refresh' },
      { value: 'neither', label: 'Neither', icon: 'arrowRight' },
    ],
    hint: 'This income/expense will be considered in your loan qualification.',
    showIf: { field: 'marital_status', values: ['divorced', 'separated'] },
  },
  {
    id: 'support_amount_received',
    question: 'How much do you receive per month in child support/alimony?',
    type: 'currency',
    placeholder: 'Monthly amount received',
    hint: 'This can count as qualifying income if documented.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_duration_received',
    question: 'How long have you been receiving this income?',
    type: 'choice',
    options: [
      { value: 'less_than_6_months', label: 'Less than 6 months', icon: 'clock' },
      { value: '6_to_12_months', label: '6-12 months', icon: 'clock' },
      { value: '1_to_3_years', label: '1-3 years', icon: 'calendar' },
      { value: 'more_than_3_years', label: 'More than 3 years', icon: 'calendar' },
    ],
    hint: 'Income must typically continue for at least 3 more years to count.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_amount_paid',
    question: 'How much do you pay per month in child support/alimony?',
    type: 'currency',
    placeholder: 'Monthly amount paid',
    hint: 'This will be factored into your debt-to-income ratio.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_type_paid',
    question: 'What type of payments are you making?',
    type: 'choice',
    options: [
      { value: 'child_support', label: 'Child Support only', icon: 'family' },
      { value: 'alimony', label: 'Alimony/Spousal Support only', icon: 'heart' },
      { value: 'both', label: 'Both Child Support and Alimony', icon: 'users' },
    ],
    hint: 'Different payment types may have different documentation requirements.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_duration_paid',
    question: 'How long will you continue making these payments?',
    type: 'choice',
    options: [
      { value: 'less_than_1_year', label: 'Less than 1 year', icon: 'clock' },
      { value: '1_to_3_years', label: '1-3 years', icon: 'calendar' },
      { value: '3_to_5_years', label: '3-5 years', icon: 'calendar' },
      { value: 'more_than_5_years', label: 'More than 5 years', icon: 'calendar' },
      { value: 'until_child_18', label: 'Until child turns 18', icon: 'family' },
    ],
    hint: 'Payments ending within 10 months may not be counted against you.',
    showIf: { field: 'child_support_alimony', values: ['pay', 'both'] },
  },
  {
    id: 'support_type_received',
    question: 'What type of payments are you receiving?',
    type: 'choice',
    options: [
      { value: 'child_support', label: 'Child Support only', icon: 'family' },
      { value: 'alimony', label: 'Alimony/Spousal Support only', icon: 'heart' },
      { value: 'both', label: 'Both Child Support and Alimony', icon: 'users' },
    ],
    hint: 'Different payment types may count differently as qualifying income.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'support_years_remaining',
    question: 'How many more years will you receive these payments?',
    type: 'choice',
    options: [
      { value: 'less_than_3_years', label: 'Less than 3 years', icon: 'clock' },
      { value: '3_to_5_years', label: '3-5 years', icon: 'calendar' },
      { value: '5_to_10_years', label: '5-10 years', icon: 'calendar' },
      { value: 'more_than_10_years', label: 'More than 10 years', icon: 'calendar' },
    ],
    hint: 'Income must typically continue for at least 3 more years to count.',
    showIf: { field: 'child_support_alimony', values: ['receive', 'both'] },
  },
  {
    id: 'property_interest',
    question: 'Do you have interest in any other real estate property?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I own property', icon: 'home' },
      { value: 'no', label: 'No other properties', icon: 'arrowRight' },
    ],
    hint: 'This includes properties you own, co-own, or have ownership interest in.',
    showIf: { field: 'first_time_buyer', values: ['no'] },
  },
  {
    id: 'property_interest_address',
    question: 'What is the address of the property you have interest in?',
    type: 'address',
    placeholder: 'Enter property address',
    hint: 'We\'ll need details about this property for your application.',
    showIf: { field: 'property_interest', values: ['yes'] },
  },
  {
    id: 'veteran',
    question: 'Have you or your spouse served in the military?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I\'m a Veteran', icon: 'medal' },
      { value: 'active', label: 'Currently Active Duty', icon: 'star' },
      { value: 'spouse', label: 'My spouse served', icon: 'heart' },
      { value: 'no', label: 'No military service', icon: 'arrowRight' },
    ],
    hint: 'Veterans can get VA loans with $0 down!',
  },
  {
    id: 'va_loan_before',
    question: 'Have you used a VA loan before?',
    type: 'choice',
    options: [
      { value: 'yes_paid_off', label: 'Yes, paid it off', icon: 'check' },
      { value: 'yes_still_have', label: 'Yes, still have it', icon: 'home' },
      { value: 'no', label: 'No, first VA loan', icon: 'star' },
    ],
    hint: 'You can use your VA benefit multiple times!',
    showIf: { field: 'veteran', values: ['yes', 'active', 'spouse'] },
  },
  {
    id: 'va_disability',
    question: 'Do you have a VA disability rating?',
    type: 'choice',
    options: [
      { value: 'yes_10_plus', label: 'Yes, 10% or higher', icon: 'shield' },
      { value: 'pending', label: 'Claim pending', icon: 'clock' },
      { value: 'no', label: 'No disability rating', icon: 'arrowRight' },
    ],
    hint: '10%+ disability rating waives the VA funding fee - saves thousands!',
    showIf: { field: 'veteran', values: ['yes', 'active'] },
  },
  {
    id: 'self_employed',
    question: 'Are you self-employed or own a business?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, self-employed', icon: 'building' },
      { value: 'side_business', label: 'I have a side business', icon: 'briefcase' },
      { value: 'no', label: 'No, I\'m a W-2\'d employee', icon: 'tie' },
    ],
    hint: 'This helps us know what income documents you\'ll need.',
  },
  {
    id: 'business_years',
    question: 'How long have you been self-employed?',
    type: 'choice',
    options: [
      { value: 'less_than_1_year', label: 'Less than 1 year', icon: 'clock' },
      { value: '1_to_2_years', label: '1-2 years', icon: 'calendar' },
      { value: 'more_than_2_years', label: 'More than 2 years', icon: 'check' },
    ],
    hint: 'Most loan programs require 2 years of self-employment history.',
    showIf: { field: 'self_employed', values: ['yes'] },
  },
  {
    id: 'business_type',
    question: 'What type of business do you have?',
    type: 'choice',
    options: [
      { value: 'sole_proprietor', label: 'Sole proprietor', icon: 'user' },
      { value: 'llc', label: 'LLC', icon: 'building' },
      { value: 's_corp', label: 'S-Corp', icon: 'briefcase' },
      { value: 'c_corp', label: 'C-Corp', icon: 'building' },
      { value: 'partnership', label: 'Partnership', icon: 'users' },
    ],
    hint: 'This determines what tax documents we\'ll need.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'prior_year_taxes_filed',
    question: 'Have you filed your prior year tax returns?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, taxes are filed', icon: 'check' },
      { value: 'no', label: 'No, not filed yet', icon: 'clock' },
      { value: 'extension', label: 'Filed an extension', icon: 'calendar' },
    ],
    hint: 'If taxes are not yet filed, we\'ll need a year-to-date Profit & Loss statement.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
    // Note: This question is dynamically shown based on date - after Jan 28 of any year
  },
  {
    id: 'write_off_expenses',
    question: 'Do you write off most expenses to minimize taxable income?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I maximize deductions', icon: 'trendDown' },
      { value: 'some', label: 'Some, but I show decent income', icon: 'balance' },
      { value: 'no', label: 'No, I show most of my income', icon: 'trendUp' },
    ],
    hint: 'Self-employed income is based on your adjusted gross income after expenses. If you write off heavily, we may need 12 months of business bank statements.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'irs_balance_owed',
    question: 'Do you have an outstanding balance owed to the IRS?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I owe the IRS', icon: 'alertTriangle' },
      { value: 'payment_plan', label: 'Yes, but on a payment plan', icon: 'clipboard' },
      { value: 'no', label: 'No outstanding balance', icon: 'check' },
    ],
    hint: 'Having a balance doesn\'t disqualify you - we just need to know.',
  },
  {
    id: 'irs_amount_owed',
    question: "What's the monthly payment?",
    type: 'currency',
    placeholder: '0',
    hint: 'This helps us understand your full financial picture.',
    showIf: { field: 'irs_balance_owed', values: ['yes', 'payment_plan'] },
  },
  {
    id: 'irs_payment_current',
    question: 'Are you current on your IRS payment plan?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, fully current', icon: 'check' },
      { value: 'behind', label: 'Behind on payments', icon: 'alertTriangle' },
    ],
    hint: 'Being current on payments is usually required for loan approval.',
    showIf: { field: 'irs_balance_owed', values: ['payment_plan'] },
  },
  {
    id: 'recent_credit_applications',
    question: 'Have you applied for any credit in the past 3 months?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I applied recently', icon: 'creditCard' },
      { value: 'no', label: 'No recent applications', icon: 'check' },
    ],
    hint: 'Car loans, credit cards, personal loans, etc. Recent inquiries can affect your score.',
  },
  {
    id: 'credit_application_type',
    question: 'What type of credit did you apply for?',
    type: 'choice',
    options: [
      { value: 'auto_loan', label: 'Auto loan', icon: 'car' },
      { value: 'credit_card', label: 'Credit card', icon: 'creditCard' },
      { value: 'personal_loan', label: 'Personal loan', icon: 'dollarSign' },
      { value: 'other', label: 'Other', icon: 'document' },
    ],
    hint: 'Recent auto loans can significantly impact your debt-to-income ratio.',
    showIf: { field: 'recent_credit_applications', values: ['yes'] },
  },
  {
    id: 'credit_application_approved',
    question: 'Was the credit application approved?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, approved', icon: 'check' },
      { value: 'pending', label: 'Still pending', icon: 'clock' },
      { value: 'no', label: 'No, denied', icon: 'x' },
    ],
    hint: 'If approved, we\'ll need to factor in the new payment.',
    showIf: { field: 'recent_credit_applications', values: ['yes'] },
  },
  {
    id: 'gift_funds',
    question: 'Will you use gift funds for your down payment?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, receiving a gift', icon: 'gift' },
      { value: 'maybe', label: 'Maybe, not sure yet', icon: 'helpCircle' },
      { value: 'no', label: 'No, using my own funds', icon: 'dollarSign' },
    ],
    hint: 'Gift funds from family are totally okay!',
  },
  {
    id: 'gift_amount',
    question: 'How much gift money will you receive?',
    type: 'currency',
    placeholder: 'Gift amount',
    hint: 'We\'ll need a gift letter from the donor.',
    showIf: { field: 'gift_funds', values: ['yes'] },
  },
  {
    id: 'gift_donor',
    question: 'Who is providing the gift?',
    type: 'choice',
    options: [
      { value: 'parent', label: 'Parent', icon: 'family' },
      { value: 'grandparent', label: 'Grandparent', icon: 'family' },
      { value: 'sibling', label: 'Sibling', icon: 'users' },
      { value: 'other_relative', label: 'Other relative', icon: 'users' },
      { value: 'non_relative', label: 'Non-relative', icon: 'user' },
    ],
    hint: 'Gift rules vary based on relationship and loan type.',
    showIf: { field: 'gift_funds', values: ['yes'] },
  },
  {
    id: 'found_property',
    question: 'Have you found a property yet?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, under contract', icon: 'document' },
      { value: 'looking', label: 'Still shopping', icon: 'search' },
      { value: 'pre_approval', label: 'Just getting pre-approved', icon: 'check' },
    ],
  },
  {
    id: 'closing_date',
    question: 'When is your target closing date?',
    type: 'choice',
    options: [
      { value: 'less_than_30', label: 'Less than 30 days', icon: 'clock' },
      { value: '30_to_45', label: '30-45 days', icon: 'calendar' },
      { value: '45_to_60', label: '45-60 days', icon: 'calendar' },
      { value: 'more_than_60', label: 'More than 60 days', icon: 'calendar' },
    ],
    hint: 'Knowing your timeline helps us prioritize appropriately.',
    showIf: { field: 'found_property', values: ['yes'] },
  },
  {
    id: 'working_with_agent',
    question: 'Are you working with a real estate agent?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, have an agent', icon: 'users' },
      { value: 'no', label: 'Not yet', icon: 'search' },
    ],
    hint: 'We can recommend great agents in your area if needed.',
  },
  {
    id: 'agent_info',
    question: 'Tell us about your real estate agent',
    type: 'agent_info',
    hint: 'Start typing to search our partner network, or enter their details manually.',
    showIf: { field: 'working_with_agent', values: ['yes'] },
  },
  {
    id: 'credit_issues',
    question: 'Have you had any credit challenges in the past 2 years?',
    type: 'choice',
    options: [
      { value: 'none', label: 'No issues', icon: 'check' },
      { value: 'late_payments', label: 'Late payments', icon: 'clock' },
      { value: 'collections', label: 'Collections/charge-offs', icon: 'alertTriangle' },
      { value: 'bankruptcy', label: 'Bankruptcy', icon: 'document' },
    ],
    hint: 'Being upfront helps us find the right program for you.',
  },
  {
    id: 'bankruptcy_type',
    question: 'What type of bankruptcy did you file?',
    type: 'choice',
    options: [
      { value: 'chapter_7', label: 'Chapter 7', icon: 'document' },
      { value: 'chapter_13', label: 'Chapter 13', icon: 'document' },
      { value: 'chapter_12', label: 'Chapter 12 (Farm/Fisherman)', icon: 'document' },
    ],
    hint: 'Different waiting periods apply for each type.',
    showIf: { field: 'credit_issues', values: ['bankruptcy'] },
  },
  {
    id: 'bankruptcy_discharge_ch7',
    question: 'When was your Chapter 7 bankruptcy discharged?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'calendar' },
      { value: '4_to_7_years', label: '4-7 years ago', icon: 'calendar' },
      { value: '8_years_or_more', label: '8 years ago or more', icon: 'check' },
    ],
    hint: 'Chapter 7 typically has a 2-4 year waiting period depending on loan type.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_7'] },
  },
  {
    id: 'chapter_13_status',
    question: 'What is the status of your Chapter 13 bankruptcy?',
    type: 'choice',
    options: [
      { value: 'active_paying', label: 'Actively paying to trustee', icon: 'clock' },
      { value: 'completed', label: 'Completed/Discharged', icon: 'check' },
    ],
    hint: 'Active Chapter 13 plans may still qualify with court approval.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_13'] },
  },
  {
    id: 'bankruptcy_discharge_ch13',
    question: 'When was your Chapter 13 bankruptcy discharged?',
    type: 'choice',
    options: [
      { value: 'less_than_2_years', label: 'Less than 2 years ago', icon: 'clock' },
      { value: '2_to_4_years', label: '2-4 years ago', icon: 'calendar' },
      { value: 'more_than_4_years', label: 'More than 4 years ago', icon: 'calendar' },
    ],
    hint: 'Chapter 13 discharge typically requires 2-4 year waiting period.',
    showIf: { field: 'chapter_13_status', values: ['completed'] },
  },
  {
    id: 'chapter_12_status',
    question: 'What is the status of your Chapter 12 bankruptcy?',
    type: 'choice',
    options: [
      { value: 'active_paying', label: 'Actively in repayment plan', icon: 'clock' },
      { value: 'completed', label: 'Completed/Discharged', icon: 'check' },
    ],
    hint: 'Chapter 12 bankruptcies require payment history and court documentation.',
    showIf: { field: 'bankruptcy_type', values: ['chapter_12'] },
  },
];

// Common employers for autocomplete
const COMMON_EMPLOYERS = [
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

// Planning questions - mortgage priorities and goals (excludes questions already asked in declarations)
const PLANNING_QUESTIONS = {
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

export default function PurchaseApplication() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Demo mode: /apply/start OR ?demo=true query parameter
  const isDemoMode = token === 'start' || searchParams.get('demo') === 'true';

  // API Configuration
  const isProduction = window.location.hostname !== 'localhost';
  const API_URL = isProduction
    ? 'https://api.perenniaai.com'
    : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

  // Storage key for auto-save
  const STORAGE_KEY = `purchase_application_${token || 'draft'}`;

  // Account & Save Progress State
  const [userAccount, setUserAccount] = useState({
    email: '',
    authMethod: null, // 'email', 'google', 'facebook', 'linkedin', 'apple'
    isLoggedIn: false,
  });
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);

  // State - All useState declarations must come before useEffect hooks that reference them
  // Initialize stage based on demo mode - check URL directly for initial state
  const [currentStage, setCurrentStage] = useState(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const isDemo = urlParams.get('demo') === 'true' || window.location.pathname.includes('/apply/start');
    return isDemo ? 'declarations' : 'account';
  });
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [residenceHistory, setResidenceHistory] = useState([
    { street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' }
  ]);
  const [coBorrowerResidenceHistory, setCoBorrowerResidenceHistory] = useState([
    { street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' }
  ]);
  const [incomeData, setIncomeData] = useState({});
  const [incomeStep, setIncomeStep] = useState(1);
  const [followupAnswers, setFollowupAnswers] = useState({});
  const [activeFollowup, setActiveFollowup] = useState(null);
  const [agentSearch, setAgentSearch] = useState('');
  const [agentSuggestions, setAgentSuggestions] = useState([]);
  const [agentLoading, setAgentLoading] = useState(false);
  const [showAgentDropdown, setShowAgentDropdown] = useState(false);
  const [agentInfo, setAgentInfo] = useState({
    name: '',
    phone: '',
    email: '',
    company: '',
    partnerId: null
  });
  const [propertyStep, setPropertyStep] = useState(1);
  const [assetData, setAssetData] = useState({});
  const [propertyData, setPropertyData] = useState({});
  const [planningData, setPlanningData] = useState({
    mortgagePriorities: [],
    personalGoals: [],
    financialPhilosophy: '',
    professionalNetwork: [],
    taxDeferredRetirement: '',
  });
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);
  const [scheduleStep, setScheduleStep] = useState(1);
  const [calendarAssignment, setCalendarAssignment] = useState(null);
  const [bookingSlots, setBookingSlots] = useState([]);
  const [bookingSelectedDate, setBookingSelectedDate] = useState(null);
  const [bookingSelectedTime, setBookingSelectedTime] = useState('');
  const [bookingWeekStart, setBookingWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingConfirmed, setBookingConfirmed] = useState(false);
  const [bookingError, setBookingError] = useState(null);
  const [planningStep, setPlanningStep] = useState(1);
  const [professionalSubStep, setProfessionalSubStep] = useState(1);
  const [wantProfessionalsInvolved, setWantProfessionalsInvolved] = useState(null);
  const [professionalContacts, setProfessionalContacts] = useState({});
  const [wantIntroductions, setWantIntroductions] = useState(null);
  const [introductionRequests, setIntroductionRequests] = useState([]);
  const [ssnRaw, setSsnRaw] = useState('');
  const [ssnDisplay, setSsnDisplay] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [currentBorrower, setCurrentBorrower] = useState(1);
  const [coBorrowerData, setCoBorrowerData] = useState({});
  const [coBorrowerIncomeData, setCoBorrowerIncomeData] = useState({});
  const [currentIncomeBorrower, setCurrentIncomeBorrower] = useState(1);
  const [coBorrowerSsnRaw, setCoBorrowerSsnRaw] = useState('');
  const [coBorrowerSsnDisplay, setCoBorrowerSsnDisplay] = useState('');
  const [paymentEstimate, setPaymentEstimate] = useState(null);
  const [eConsentAgreed, setEConsentAgreed] = useState(false);
  const [creditAuthAgreed, setCreditAuthAgreed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [showSubmissionSuccess, setShowSubmissionSuccess] = useState(false);
  const [portalUrlForRedirect, setPortalUrlForRedirect] = useState(null);
  const portalUrlRef = useRef(null); // Ref to avoid closure issues in setTimeout
  const [employerSuggestions, setEmployerSuggestions] = useState([]);
  const [showEmployerDropdown, setShowEmployerDropdown] = useState(false);

  // Application configuration (loaded from backend)
  const [applicationConfig, setApplicationConfig] = useState(null);
  const [configLoaded, setConfigLoaded] = useState(false);

  // Stubs for disabled followup feature
  const clearFollowup = () => {};
  const checkForFollowup = async () => null;

  // Load application configuration from backend (slide customization)
  useEffect(() => {
    const loadApplicationConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/settings/application-slides`);
        if (response.ok) {
          const config = await response.json();
          setApplicationConfig(config);
          console.log('[PurchaseApplication] Loaded custom configuration:', {
            stages: config.stages?.filter(s => s.enabled).length,
            questions: config.declarationQuestions?.filter(q => q.enabled).length
          });
        }
      } catch (error) {
        console.warn('[PurchaseApplication] Failed to load config, using defaults:', error);
      } finally {
        setConfigLoaded(true);
      }
    };
    loadApplicationConfig();
  }, [API_URL]);

  // Get enabled stages based on configuration
  const getEnabledStages = useCallback(() => {
    if (!applicationConfig?.stages) return STAGES;

    // Create a map of config by stage id for quick lookup
    const configMap = new Map(applicationConfig.stages.map(s => [s.id, s]));

    // Filter and reorder stages based on config
    return applicationConfig.stages
      .filter(configStage => configStage.enabled)
      .map(configStage => {
        // Find the original stage definition and merge with config
        const originalStage = STAGES.find(s => s.id === configStage.id);
        return originalStage ? { ...originalStage, ...configStage } : configStage;
      });
  }, [applicationConfig]);

  // Get enabled declaration questions based on configuration
  const getEnabledQuestions = useCallback(() => {
    if (!applicationConfig?.declarationQuestions) return DECLARATION_QUESTIONS;

    // Create a set of enabled question IDs
    const enabledIds = new Set(
      applicationConfig.declarationQuestions
        .filter(q => q.enabled)
        .map(q => q.id)
    );

    // Filter original questions to only include enabled ones, preserving full question data
    return DECLARATION_QUESTIONS.filter(q => enabledIds.has(q.id));
  }, [applicationConfig]);

  // Memoized enabled stages and questions
  const enabledStages = getEnabledStages();
  const enabledQuestions = getEnabledQuestions();
  const visibleStages = enabledStages.filter(s => !s.hideFromProgress);

  // Load saved progress from localStorage on mount (unless fresh=true)
  useEffect(() => {
    // Check if this is a fresh start (clear previous progress)
    const isFreshStart = searchParams.get('fresh') === 'true';

    if (isFreshStart) {
      // Clear saved progress for a fresh start
      localStorage.removeItem(STORAGE_KEY);
      console.log('[PurchaseApplication] Fresh start - cleared saved progress');
      // Remove the fresh param from URL without reload
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('fresh');
      window.history.replaceState({}, '', newUrl.toString());
      return; // Don't load saved data
    }

    const savedData = localStorage.getItem(STORAGE_KEY);
    if (savedData) {
      try {
        const parsed = JSON.parse(savedData);
        if (parsed.declarations) setDeclarations(parsed.declarations);
        if (parsed.profileData) setProfileData(parsed.profileData);
        if (parsed.incomeData) setIncomeData(parsed.incomeData);
        if (parsed.assetData) setAssetData(parsed.assetData);
        if (parsed.propertyData) setPropertyData(parsed.propertyData);
        if (parsed.coBorrowerData) setCoBorrowerData(parsed.coBorrowerData);
        if (parsed.coBorrowerIncomeData) setCoBorrowerIncomeData(parsed.coBorrowerIncomeData);
        if (parsed.currentStage && parsed.currentStage !== 'account') {
          setCurrentStage(parsed.currentStage);
        }
        if (parsed.userAccount?.email) {
          setUserAccount(parsed.userAccount);
        }
        setLastSavedAt(parsed.savedAt ? new Date(parsed.savedAt) : null);
        console.log('Loaded saved application progress');
      } catch (e) {
        console.error('Failed to load saved progress:', e);
      }
    }
  }, [STORAGE_KEY, searchParams]);

  // Handle auth token from magic link login
  useEffect(() => {
    const authToken = searchParams.get('auth');
    if (authToken) {
      try {
        // Decode JWT to get user info (without verification - server already verified)
        const parts = authToken.split('.');
        if (parts.length === 3) {
          const payload = JSON.parse(atob(parts[1]));
          const email = payload.sub || payload.email;
          if (email) {
            // Clear any old cached data when logging in fresh via magic link
            // This ensures we don't show stale personalized data from previous sessions
            localStorage.removeItem(STORAGE_KEY);
            console.log('[PurchaseApplication] Cleared old data for fresh magic link login');

            // Reset all form data to initial state
            setDeclarations({});
            setProfileData({ firstName: '', lastName: '', email: email, phone: '', dateOfBirth: '' });
            setIncomeData({});
            setAssetData({ checking: '', savings: '', investments: '', retirement: '', other: '' });
            setPropertyData({});
            setCoBorrowerData({});
            setCoBorrowerIncomeData({});

            setUserAccount({
              email: email,
              authMethod: 'email',
              isLoggedIn: true,
              authToken: authToken,
            });
            // Skip account stage and go to declarations
            setCurrentStage('declarations');
            // Clean up URL
            const newUrl = new URL(window.location.href);
            newUrl.searchParams.delete('auth');
            window.history.replaceState({}, '', newUrl.toString());
            console.log('[PurchaseApplication] Logged in via magic link:', email);
          }
        }
      } catch (e) {
        console.error('Failed to parse auth token:', e);
      }
    }
  }, [searchParams, STORAGE_KEY]);

  // Skip account stage in demo mode
  useEffect(() => {
    if (isDemoMode && currentStage === 'account') {
      setCurrentStage('declarations');
    }
  }, [isDemoMode, currentStage]);

  // Auto-save to localStorage whenever data changes
  useEffect(() => {
    // Don't save on initial mount or if on account stage
    if (currentStage === 'account') return;

    // Strip SSN and other NPI (GLBA) fields before saving to localStorage
    const sanitizedProfileData = { ...profileData };
    delete sanitizedProfileData.ssn;
    const sanitizedCoBorrowerData = { ...coBorrowerData };
    delete sanitizedCoBorrowerData.ssn;

    // Exclude financial NPI from localStorage auto-save (income, assets, co-borrower income)
    // These contain employer info, salary, bank balances — Non-Public Information under GLBA
    const dataToSave = {
      declarations,
      profileData: sanitizedProfileData,
      // incomeData, assetData, coBorrowerIncomeData intentionally excluded — NPI
      propertyData,
      coBorrowerData: sanitizedCoBorrowerData,
      currentStage,
      userAccount,
      savedAt: new Date().toISOString(),
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
    setLastSavedAt(new Date());
  }, [declarations, profileData, incomeData, assetData, propertyData, coBorrowerData, coBorrowerIncomeData, currentStage, userAccount, STORAGE_KEY]);

  // US States for dropdown
  const US_STATES = [
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

  // Calculate total months of residence history
  const calculateTotalResidenceMonths = (history) => {
    return history.reduce((total, addr) => {
      const years = parseInt(addr.years) || 0;
      const months = parseInt(addr.months) || 0;
      return total + (years * 12) + months;
    }, 0);
  };

  // Check if we need more residence history (< 24 months)
  const needsMoreResidenceHistory = (history) => {
    return calculateTotalResidenceMonths(history) < 24;
  };

  // Add a new address to residence history
  const addResidenceAddress = (isCoBorrower = false) => {
    const newAddress = { street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' };
    if (isCoBorrower) {
      setCoBorrowerResidenceHistory(prev => [...prev, newAddress]);
    } else {
      setResidenceHistory(prev => [...prev, newAddress]);
    }
  };

  // Remove an address from residence history
  const removeResidenceAddress = (index, isCoBorrower = false) => {
    if (isCoBorrower) {
      setCoBorrowerResidenceHistory(prev => prev.filter((_, i) => i !== index));
    } else {
      setResidenceHistory(prev => prev.filter((_, i) => i !== index));
    }
  };

  // Update a specific address in residence history
  const updateResidenceAddress = (index, field, value, isCoBorrower = false) => {
    if (isCoBorrower) {
      setCoBorrowerResidenceHistory(prev => prev.map((addr, i) =>
        i === index ? { ...addr, [field]: value } : addr
      ));
    } else {
      setResidenceHistory(prev => prev.map((addr, i) =>
        i === index ? { ...addr, [field]: value } : addr
      ));
    }
  };

  // Handle URL query parameters - navigate to specific stage if requested
  useEffect(() => {
    const stageParam = searchParams.get('stage');
    if (stageParam === 'calculator') {
      // Navigate to the planning stage which contains the payment calculator
      setCurrentStage('planning');
      setPlanningStep(1); // Step 1 is the payment calculator
    }
  }, [searchParams]);

  // Fetch calendar assignment for scheduling
  useEffect(() => {
    const fetchCalendarAssignment = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/calendar-assignments/purchase_application`);
        if (response.ok) {
          const data = await response.json();
          setCalendarAssignment(data);
        }
      } catch (err) {
        console.error('Error fetching calendar assignment:', err);
      }
    };
    fetchCalendarAssignment();
  }, [API_URL]);

  // Keep ref in sync with state to avoid closure issues
  useEffect(() => {
    portalUrlRef.current = portalUrlForRedirect;
  }, [portalUrlForRedirect]);

  // Auto-redirect to client portal after successful submission
  useEffect(() => {
    if (showSubmissionSuccess) {
      const redirectTimer = setTimeout(() => {
        // Use ref to get latest portal URL (avoids closure capturing stale state)
        let redirectUrl = portalUrlRef.current;

        console.log('[PurchaseApplication] Redirect check - portalUrlRef:', portalUrlRef.current);

        // If no portal URL provided, construct one from current location
        if (!redirectUrl) {
          // Use perenniaai.com for production, current host for dev
          const isProduction = window.location.hostname.includes('perenniaai.com');
          const baseHost = isProduction ? 'www.perenniaai.com' : window.location.host;
          const protocol = isProduction ? 'https' : window.location.protocol.replace(':', '');

          // Try to get the LO slug from the current URL (e.g., /lo/tim-loss or /apply/tim-loss)
          const pathMatch = window.location.pathname.match(/\/(?:lo|apply)\/([^/]+)/);
          const potentialSlug = pathMatch ? pathMatch[1] : null;
          // Exclude reserved route names that aren't LO slugs
          const reservedSlugs = ['purchase', 'refinance', 'login', 'start', 'oauth', 'verify'];
          const loSlug = potentialSlug && !reservedSlugs.includes(potentialSlug.toLowerCase()) ? potentialSlug : null;

          if (loSlug) {
            // Redirect to the LO's microsite (which has client portal features)
            redirectUrl = `${protocol}://${baseHost}/lo/${loSlug}`;
          } else {
            // Check if borrower email is available for magic link
            const borrowerEmail = localStorage.getItem('borrower_email');
            if (borrowerEmail) {
              // Redirect to borrower portal with email for magic link
              redirectUrl = `${protocol}://${baseHost}/borrower-portal?email=${encodeURIComponent(borrowerEmail)}&submitted=true`;
            } else {
              // Final fallback: redirect to thank you page
              redirectUrl = `${protocol}://${baseHost}/application-submitted`;
            }
          }
          console.log('[PurchaseApplication] Fallback redirect to:', redirectUrl);
        }

        // Signal to parent iframe that submission is complete (if embedded)
        if (window.parent !== window) {
          window.parent.postMessage({ type: 'APPLICATION_SUBMITTED', portalUrl: redirectUrl }, window.location.origin);
        }

        // Redirect to the client portal
        window.location.href = redirectUrl;
      }, 3000); // 3 second delay to show success message

      return () => clearTimeout(redirectTimer);
    }
  }, [showSubmissionSuccess]);

  // Handle SSN input with masking - shows XXX-XX-1234 format
  const handleSsnChange = (input, isCoBorrower = false) => {
    // Remove all non-digits
    const digits = input.replace(/\D/g, '').slice(0, 9);

    // Format display with masking
    let display = '';
    if (digits.length === 0) {
      display = '';
    } else if (digits.length <= 3) {
      display = 'X'.repeat(digits.length);
    } else if (digits.length <= 5) {
      display = 'XXX-' + 'X'.repeat(digits.length - 3);
    } else {
      const last4 = digits.slice(5);
      display = 'XXX-XX-' + last4;
    }

    if (isCoBorrower) {
      setCoBorrowerSsnRaw(digits);
      setCoBorrowerSsnDisplay(display);
      setCoBorrowerData(prev => ({ ...prev, ssn: digits }));
    } else {
      setSsnRaw(digits);
      setSsnDisplay(display);
      setProfileData(prev => ({ ...prev, ssn: digits }));
    }
  };

  // Check if multiple borrowers based on declaration
  const hasMultipleBorrowers = ['2', '3', '4+'].includes(declarations.borrower_count);

  // Get borrower count as number
  const getBorrowerCount = () => {
    if (declarations.borrower_count === '2') return 2;
    if (declarations.borrower_count === '3') return 3;
    if (declarations.borrower_count === '4+') return 4;
    return 1;
  };

  // Filter employers
  const filterEmployers = (input) => {
    if (!input || input.length < 2) {
      setEmployerSuggestions([]);
      setShowEmployerDropdown(false);
      return;
    }
    const filtered = COMMON_EMPLOYERS.filter(emp =>
      emp.toLowerCase().includes(input.toLowerCase())
    ).slice(0, 8);
    setEmployerSuggestions(filtered);
    setShowEmployerDropdown(filtered.length > 0);
  };

  // Search realtors from CRM partner database
  const searchRealtors = async (searchTerm) => {
    if (!searchTerm || searchTerm.length < 2) {
      setAgentSuggestions([]);
      setShowAgentDropdown(false);
      return;
    }

    setAgentLoading(true);
    try {
      const response = await fetch(
        `${API_URL}/api/v1/public/partners/realtors?q=${encodeURIComponent(searchTerm)}&limit=8`
      );
      if (response.ok) {
        const data = await response.json();
        setAgentSuggestions(data);
        setShowAgentDropdown(data.length > 0);
      }
    } catch (error) {
      console.error('Error searching realtors:', error);
    } finally {
      setAgentLoading(false);
    }
  };

  // Handle selecting an agent from autocomplete
  const handleSelectAgent = (agent) => {
    setAgentInfo({
      name: agent.name || '',
      phone: agent.phone || '',
      email: agent.email || '',
      company: agent.company || '',
      partnerId: agent.id || null
    });
    setAgentSearch(agent.name || '');
    setShowAgentDropdown(false);
    // Also update declarations for form submission
    setDeclarations(prev => ({
      ...prev,
      agent_name: agent.name || '',
      agent_phone: agent.phone || '',
      agent_email: agent.email || '',
      agent_company: agent.company || '',
      agent_partner_id: agent.id || null
    }));
  };

  // Handle manual agent info changes
  const handleAgentInfoChange = (field, value) => {
    setAgentInfo(prev => ({ ...prev, [field]: value }));
    // Also update declarations
    setDeclarations(prev => ({
      ...prev,
      [`agent_${field}`]: value
    }));
  };

  // Calculate progress (use visibleStages to exclude hidden stages like 'account')
  const getProgress = useCallback(() => {
    const stageIndex = visibleStages.findIndex(s => s.id === currentStage);
    // If current stage is hidden (like 'account'), return 0
    if (stageIndex === -1) return 0;
    const stageProgress = (stageIndex / visibleStages.length) * 100;
    if (currentStage === 'declarations') {
      const questionProgress = (currentQuestionIndex / enabledQuestions.length) * (100 / visibleStages.length);
      return Math.round(stageProgress + questionProgress);
    }
    return Math.round(stageProgress);
  }, [currentStage, currentQuestionIndex, visibleStages, enabledQuestions]);

  // Helper to check if a question should be shown based on conditions
  const shouldShowQuestion = useCallback((question, currentDeclarations) => {
    // Check hideIf condition first - if matches, hide the question
    if (question.hideIf) {
      const { field, values } = question.hideIf;
      if (values.includes(currentDeclarations[field])) {
        return false;
      }
    }
    // Then check showIf condition
    if (!question.showIf) return true;
    const { field, values } = question.showIf;
    return values.includes(currentDeclarations[field]);
  }, []);

  // Get filtered questions based on current declarations
  const getVisibleQuestions = useCallback(() => {
    return enabledQuestions.filter(q => shouldShowQuestion(q, declarations));
  }, [declarations, shouldShowQuestion, enabledQuestions]);

  // Update needs list
  useEffect(() => {
    const newNeeds = [];

    // Government ID is always required
    newNeeds.push({ id: 'id', label: "Driver's license or passport", category: 'identity' });

    // Green Card required for non-US citizens
    if (declarations.citizenship_status && declarations.citizenship_status !== 'us_citizen') {
      newNeeds.push({ id: 'green_card', label: 'Unexpired Green Card (front & back)', category: 'identity' });

      // For visa holders, also need work authorization
      if (declarations.citizenship_status === 'non_permanent_resident') {
        newNeeds.push({ id: 'visa_docs', label: 'Visa documentation (I-94, EAD, etc.)', category: 'identity' });
      }
    }

    if (declarations.self_employed === 'yes' || declarations.self_employed === 'side_business') {
      newNeeds.push({ id: 'tax_returns', label: '2 years tax returns', category: 'income' });
      newNeeds.push({ id: 'profit_loss', label: 'Year-to-date P&L statement', category: 'income' });

      // If they write off heavily, need 12 months business bank statements
      if (declarations.write_off_expenses === 'yes') {
        newNeeds.push({ id: 'business_bank_statements', label: '12 months business bank statements', category: 'income' });
      }
    } else {
      newNeeds.push({ id: 'paystubs', label: 'Recent pay stubs (30 days)', category: 'income' });
      newNeeds.push({ id: 'w2', label: 'W-2s (last 2 years)', category: 'income' });
    }

    if (declarations.gift_funds === 'yes') {
      newNeeds.push({ id: 'gift_letter', label: 'Gift letter from donor', category: 'assets' });
      newNeeds.push({ id: 'gift_source', label: 'Donor bank statements', category: 'assets' });
    }

    if (declarations.veteran && declarations.veteran !== 'no') {
      newNeeds.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
    }

    // IRS payment plan documentation
    if (declarations.irs_balance_owed === 'yes' || declarations.irs_balance_owed === 'payment_plan') {
      newNeeds.push({ id: 'irs_docs', label: 'IRS payment arrangement documentation', category: 'legal' });
    }

    // New credit account statement (if approved)
    if (declarations.credit_application_approved === 'yes') {
      newNeeds.push({ id: 'new_account_statement', label: 'New account statement (loan/credit card)', category: 'assets' });
    }

    newNeeds.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });

    if (declarations.found_property === 'yes') {
      newNeeds.push({ id: 'purchase_contract', label: 'Purchase contract', category: 'property' });
    }

    setNeedsList(newNeeds);
  }, [declarations]);

  // Micro-win animation
  const showMicroWinAnimation = (message) => {
    setMicroWinMessage(message);
    setShowMicroWin(true);
    setTimeout(() => setShowMicroWin(false), 2500);
  };

  // Handle application submission
  const handleSubmitApplication = async () => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // Get loan officer ID from token if available (from microsite)
      let loId = null;
      if (token && token !== 'start') {
        // Token might contain LO info - try to extract from localStorage or context
        const storedLoId = localStorage.getItem('lo_id');
        if (storedLoId) {
          loId = storedLoId;
        }
      }

      const submissionData = {
        profileData,
        incomeData,
        assetData,
        propertyData,
        declarations,
        paymentEstimate,
        eConsentAgreed,
        creditAuthAgreed,
        loId,
      };

      const response = await fetch(`${API_URL}/api/v1/borrower-auth/submit-application`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(submissionData),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Submission failed');
      }

      console.log('[PurchaseApplication] Submit response:', result);
      console.log('[PurchaseApplication] Portal URL from response:', result.data?.portal_url);

      // Store borrower email for fallback magic link
      if (profileData?.email) {
        localStorage.setItem('borrower_email', profileData.email);
      }

      // Sync document requirements to Smart Docs portal
      if (result.data?.loan_id) {
        try {
          // Get the calculated document requirements using the same function as the sidebar
          const coBorrowerInfo = declarations.borrower_count && ['2', '3', '4+'].includes(declarations.borrower_count)
            ? { firstName: declarations.co_borrower_first_name }
            : {};
          const coBorrowerIncomeInfo = { employerName: declarations.co_borrower_employer_name };

          const requiredDocs = getRequiredDocuments(
            declarations,
            assetData,
            profileData,
            incomeData,
            coBorrowerInfo,
            coBorrowerIncomeInfo
          );

          // Call the sync endpoint
          const syncResponse = await fetch(`${API_URL}/api/v1/smart-docs/needs-list/sync-from-application`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              loan_id: result.data.loan_id,
              workspace_slug: result.data.workspace_slug,
              borrower_first_name: profileData.firstName || 'Borrower',
              co_borrower_first_name: coBorrowerInfo.firstName || null,
              documents: requiredDocs.map(doc => ({
                id: doc.id,
                name: doc.name,
                description: doc.description,
                category: doc.category,
                stage: doc.stage,
              })),
            }),
          });

          const syncResult = await syncResponse.json();
          console.log('[PurchaseApplication] Smart Docs sync result:', syncResult);
        } catch (syncError) {
          // Non-critical - log but don't fail the submission
          console.warn('[PurchaseApplication] Failed to sync documents to Smart Docs (non-critical):', syncError);
        }
      }

      // Clear saved PII from localStorage after successful submission
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem('borrower_email');

      // Success - show the submission success lightbox
      if (result.data?.portal_url) {
        console.log('[PurchaseApplication] Setting portal URL:', result.data.portal_url);
        setPortalUrlForRedirect(result.data.portal_url);
        portalUrlRef.current = result.data.portal_url; // Set ref immediately to avoid timing issues
      } else {
        console.warn('[PurchaseApplication] No portal_url in response, will use fallback');
      }
      setShowSubmissionSuccess(true);
    } catch (error) {
      console.error('Application submission error:', error);
      setSubmitError(error.message || 'Failed to submit application. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle follow-up answers submitted
  const handleFollowupSubmit = (answers, trigger) => {
    // Store follow-up answers
    setFollowupAnswers(prev => ({
      ...prev,
      [trigger]: answers
    }));
    // Also merge into declarations for form submission
    setDeclarations(prev => ({
      ...prev,
      ...Object.entries(answers).reduce((acc, [key, val]) => {
        acc[`${trigger}_${key}`] = val;
        return acc;
      }, {})
    }));
    // Clear active follow-up and continue to next question
    setActiveFollowup(null);
    clearFollowup();
    proceedToNextQuestion();
  };

  // Handle skipping follow-up
  const handleFollowupSkip = () => {
    setActiveFollowup(null);
    clearFollowup();
    proceedToNextQuestion();
  };

  // Handle follow-up for income/asset stages (doesn't navigate to next question)
  const handleStageFollowupSubmit = (answers, trigger) => {
    setFollowupAnswers(prev => ({
      ...prev,
      [trigger]: answers
    }));
    setActiveFollowup(null);
    clearFollowup();
  };

  const handleStageFollowupSkip = () => {
    setActiveFollowup(null);
    clearFollowup();
  };

  // Check for follow-ups when income data changes
  const handleIncomeFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));

    // Trigger follow-up check for specific fields
    const triggerFields = ['businessType', 'ownershipPercent', 'rentalIncome', 'otherIncome'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(
        `income_${fieldName}`,
        value,
        'purchase',
        { ...declarations, ...incomeData, [fieldName]: value }
      );
      if (result && result.needs_followup) {
        setActiveFollowup(result);
      }
    }
  };

  // Check for follow-ups when asset data changes
  const handleAssetFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));

    // Trigger follow-up check for large deposits or gift-related fields
    const triggerFields = ['largeDeposits', 'giftAmount', 'donorName', 'otherAssets'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(
        `asset_${fieldName}`,
        value,
        'purchase',
        { ...declarations, ...assetData, [fieldName]: value }
      );
      if (result && result.needs_followup) {
        setActiveFollowup(result);
      }
    }
  };

  // Proceed to next question
  const proceedToNextQuestion = () => {
    let nextIndex = currentQuestionIndex + 1;
    while (nextIndex < enabledQuestions.length) {
      const nextQuestion = enabledQuestions[nextIndex];
      if (shouldShowQuestion(nextQuestion, declarations)) {
        setCurrentQuestionIndex(nextIndex);
        return;
      }
      nextIndex++;
    }
    // If no more questions, go to next enabled stage after declarations
    goToNextStage();
  };

  // Handle declaration answer
  const handleDeclarationAnswer = async (questionId, value) => {
    setIsAnimating(true);
    const newDeclarations = { ...declarations, [questionId]: value };
    setDeclarations(newDeclarations);

    // Check for AI follow-up questions on complex situations
    const triggerFields = ['self_employed', 'gift_funds', 'bankruptcy', 'credit_issues', 'investment_property', 'coborrower'];
    if (triggerFields.some(f => questionId.includes(f))) {
      const result = await checkForFollowup(questionId, value, 'purchase', newDeclarations);
      if (result && result.needs_followup) {
        setActiveFollowup(result);
        setIsAnimating(false);
        return; // Don't proceed to next question yet
      }
    }

    setTimeout(() => {
      setIsAnimating(false);

      // Find next visible question
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < enabledQuestions.length) {
        const nextQuestion = enabledQuestions[nextIndex];
        if (shouldShowQuestion(nextQuestion, newDeclarations)) {
          setCurrentQuestionIndex(nextIndex);
          return;
        }
        nextIndex++;
      }

      // No more visible questions - move to next stage
      showMicroWinAnimation('Great! Your checklist is ready!');
      setTimeout(() => goToNextStage(), 1500);
    }, 300);
  };

  // Go back to previous visible question
  const goToPrevQuestion = () => {
    let prevIndex = currentQuestionIndex - 1;
    while (prevIndex >= 0) {
      const prevQuestion = enabledQuestions[prevIndex];
      if (shouldShowQuestion(prevQuestion, declarations)) {
        setCurrentQuestionIndex(prevIndex);
        return;
      }
      prevIndex--;
    }
  };

  // Get current visible question number for display
  const getVisibleQuestionNumber = () => {
    const visibleQuestions = getVisibleQuestions();
    const currentQuestion = enabledQuestions[currentQuestionIndex];
    return visibleQuestions.findIndex(q => q.id === currentQuestion?.id) + 1;
  };

  // Navigation
  const goToNextStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex < enabledStages.length - 1) {
      setCurrentStage(enabledStages[currentIndex + 1].id);
      showMicroWinAnimation(getStageMicroWin(enabledStages[currentIndex].id));
    }
  };

  const goToPrevStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) {
      setCurrentStage(enabledStages[currentIndex - 1].id);
    }
  };

  const getStageMicroWin = (stageId) => {
    const wins = {
      declarations: 'Great start!',
      profile: 'Profile complete!',
      income: 'Income captured!',
      assets: 'Assets recorded!',
      property: 'Almost done!',
    };
    return wins[stageId] || 'Section complete!';
  };

  // Render declarations
  // Handle input-type declaration answers (currency, address)
  const handleInputAnswer = (questionId, value) => {
    setDeclarations(prev => ({ ...prev, [questionId]: value }));
  };

  const submitInputAnswer = (questionId) => {
    if (declarations[questionId]) {
      setIsAnimating(true);
      setTimeout(() => {
        setIsAnimating(false);
        // Find next visible question
        let nextIndex = currentQuestionIndex + 1;
        while (nextIndex < enabledQuestions.length) {
          const nextQuestion = enabledQuestions[nextIndex];
          if (shouldShowQuestion(nextQuestion, declarations)) {
            setCurrentQuestionIndex(nextIndex);
            return;
          }
          nextIndex++;
        }
        // No more visible questions - move to next stage
        showMicroWinAnimation('Great! Your checklist is ready!');
        setTimeout(() => goToNextStage(), 1500);
      }, 300);
    }
  };

  // Render account creation/login stage
  const renderAccountStage = () => {
    const handleSocialLogin = (provider) => {
      // Redirect to OAuth connect endpoint
      const providerLower = provider.toLowerCase();
      const returnUrl = encodeURIComponent(window.location.href);
      window.location.href = `${API_URL}/api/v1/borrower-auth/${providerLower}/connect?return_url=${returnUrl}`;
    };

    const handleEmailContinue = async () => {
      if (!userAccount.email || !userAccount.email.includes('@')) {
        toast.error('Please enter a valid email address');
        return;
      }

      setEmailSending(true);
      try {
        const response = await fetch(`${API_URL}/api/v1/borrower-auth/email/request`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: userAccount.email,
            first_name: userAccount.firstName || '',
            last_name: userAccount.lastName || ''
          })
        });

        if (response.ok) {
          setEmailSent(true);
        } else {
          const data = await response.json();
          toast.error(data.detail || 'Failed to send login link. Please try again.');
        }
      } catch (error) {
        console.error('Email login error:', error);
        toast.error('Failed to send login link. Please try again.');
      } finally {
        setEmailSending(false);
      }
    };

    return (
      <div className="stage-content account-creation-stage">
        <div className="stage-header" style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h2>Let's Get Started</h2>
          <p>Create an account to save your progress and come back anytime</p>
        </div>

        <div className="form-card" style={{ maxWidth: '480px', margin: '0 auto' }}>
          {/* Social Login Options */}
          <div className="social-login-section" style={{ marginBottom: '24px' }}>
            <p style={{ textAlign: 'center', color: '#6b7280', marginBottom: '16px', fontSize: '14px' }}>
              Sign up with
            </p>
            <div className="social-buttons" style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '12px',
              marginBottom: '16px'
            }}>
              <button
                onClick={() => handleSocialLogin('Google')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '12px 16px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                  transition: 'all 0.2s'
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Google
              </button>
              <button
                onClick={() => handleSocialLogin('Facebook')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '12px 16px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                  transition: 'all 0.2s'
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#1877F2">
                  <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                </svg>
                Facebook
              </button>
              <button
                onClick={() => handleSocialLogin('LinkedIn')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '12px 16px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                  transition: 'all 0.2s'
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#0A66C2">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
                LinkedIn
              </button>
              <button
                onClick={() => handleSocialLogin('Apple')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '12px 16px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                  transition: 'all 0.2s'
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#000000">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                </svg>
                Apple
              </button>
            </div>

            <div className="divider" style={{
              display: 'flex',
              alignItems: 'center',
              gap: '16px',
              margin: '24px 0'
            }}>
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }}></div>
              <span style={{ color: '#9ca3af', fontSize: '14px' }}>or continue with email</span>
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }}></div>
            </div>
          </div>

          {/* Email Input */}
          <div className="email-section">
            {emailSent ? (
              <div style={{
                textAlign: 'center',
                padding: '24px',
                background: '#f0fdf4',
                borderRadius: '12px',
                border: '1px solid #bbf7d0'
              }}>
                <div style={{ fontSize: '48px', marginBottom: '16px' }}>✉️</div>
                <h3 style={{ margin: '0 0 8px', color: '#166534', fontSize: '18px' }}>Check Your Email</h3>
                <p style={{ margin: '0 0 16px', color: '#15803d', fontSize: '14px' }}>
                  We sent a login link to <strong>{userAccount.email}</strong>
                </p>
                <p style={{ margin: 0, color: '#6b7280', fontSize: '13px' }}>
                  Click the link in the email to continue your application.
                </p>
                <button
                  onClick={() => setEmailSent(false)}
                  style={{
                    marginTop: '16px',
                    background: 'transparent',
                    border: 'none',
                    color: '#0ea5e9',
                    cursor: 'pointer',
                    fontSize: '14px',
                    textDecoration: 'underline'
                  }}
                >
                  Use a different email
                </button>
              </div>
            ) : (
              <>
                <div className="form-group" style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>Email Address</label>
                  <input
                    type="email"
                    value={userAccount.email}
                    onChange={(e) => setUserAccount(prev => ({ ...prev, email: e.target.value }))}
                    placeholder="you@example.com"
                    className="fun-input"
                    style={{ width: '100%' }}
                    disabled={emailSending}
                  />
                </div>
                <button
                  onClick={handleEmailContinue}
                  className="btn-continue"
                  style={{ width: '100%', marginBottom: '12px' }}
                  disabled={emailSending || !userAccount.email?.includes('@')}
                >
                  {emailSending ? 'Sending...' : 'Continue with Email →'}
                </button>
              </>
            )}
          </div>

          {/* Login Option for Existing Users */}
          <div style={{
            textAlign: 'center',
            marginTop: '20px',
            padding: '16px',
            background: '#f0f9ff',
            borderRadius: '8px',
            border: '1px solid #bae6fd'
          }}>
            <p style={{ margin: '0 0 12px', color: '#0369a1', fontSize: '14px', fontWeight: 500 }}>
              Already started an application?
            </p>
            <button
              onClick={() => navigate('/apply/login')}
              style={{
                background: '#0ea5e9',
                color: 'white',
                border: 'none',
                padding: '10px 24px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'background 0.2s'
              }}
              onMouseOver={(e) => e.target.style.background = '#0284c7'}
              onMouseOut={(e) => e.target.style.background = '#0ea5e9'}
            >
              Log In to Continue
            </button>
          </div>

          {/* Benefits */}
          <div className="account-benefits" style={{
            marginTop: '24px',
            padding: '16px',
            background: '#f9fafb',
            borderRadius: '8px'
          }}>
            <p style={{ fontWeight: 600, fontSize: '14px', marginBottom: '12px', color: '#374151' }}>
              Why create an account?
            </p>
            <ul style={{ margin: 0, paddingLeft: '20px', color: '#6b7280', fontSize: '13px', lineHeight: '1.8' }}>
              <li>Save your progress and return anytime</li>
              <li>Get a personalized experience</li>
              <li>Track your application status</li>
              <li>Receive updates from your loan officer</li>
            </ul>
          </div>

          {/* Demo Mode Button - Skip account creation */}
          {isDemoMode && (
            <div style={{ marginTop: '24px', textAlign: 'center' }}>
              <button
                onClick={() => setCurrentStage('declarations')}
                style={{
                  padding: '12px 32px',
                  background: '#6366f1',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '16px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                Continue in Demo Mode
              </button>
              <p style={{ marginTop: '8px', fontSize: '12px', color: '#9ca3af' }}>
                Skip account creation for testing purposes
              </p>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderDeclarationsStage = () => {
    const question = enabledQuestions[currentQuestionIndex];
    const visibleQuestions = getVisibleQuestions();
    const visibleQuestionNum = getVisibleQuestionNumber();

    // Guard: if question is undefined, reset to first question
    if (!question) {
      setCurrentQuestionIndex(0);
      return <div className="stage-content">Loading...</div>;
    }

    // Render different input types
    const renderQuestionInput = () => {
      if (question.type === 'currency') {
        return (
          <div className="declaration-input-container">
            <div className="currency-input-wrapper" style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              maxWidth: '300px',
              margin: '0 auto'
            }}>
              <span style={{
                fontSize: '24px',
                fontWeight: '500',
                color: '#374151'
              }}>$</span>
              <input
                type="number"
                className="declaration-currency-input fun-input"
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
                placeholder={question.placeholder || '0'}
                onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
                style={{
                  textAlign: 'center',
                  fontSize: '20px',
                  fontWeight: '500',
                  flex: 1
                }}
              />
              <span style={{
                fontSize: '16px',
                fontWeight: '500',
                color: '#6b7280'
              }}>/month</span>
            </div>
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      if (question.type === 'address') {
        return (
          <div className="declaration-input-container">
            <div className="address-input-wrapper">
              <Icon name="mapPin" size={20} className="address-icon" />
              <input
                type="text"
                className="declaration-address-input fun-input"
                value={declarations[question.id] || ''}
                onChange={(e) => handleInputAnswer(question.id, e.target.value)}
                placeholder={question.placeholder || 'Enter address'}
                onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
              />
            </div>
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Text input type
      if (question.type === 'text') {
        return (
          <div className="declaration-input-container">
            <input
              type="text"
              className="declaration-text-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              placeholder={question.placeholder || 'Enter your answer'}
              onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
            />
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      // State select dropdown type
      if (question.type === 'state_select') {
        return (
          <div className="declaration-input-container">
            <select
              className="declaration-text-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              style={{
                fontSize: '18px',
                padding: '16px 20px',
                maxWidth: '400px',
                margin: '0 auto',
                display: 'block',
                cursor: 'pointer'
              }}
            >
              {US_STATES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
              style={{ marginTop: '20px' }}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Phone input type
      if (question.type === 'phone') {
        return (
          <div className="declaration-input-container">
            <input
              type="tel"
              className="declaration-text-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              placeholder={question.placeholder || '(555) 555-5555'}
              onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
            />
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Email input type
      if (question.type === 'email') {
        return (
          <div className="declaration-input-container">
            <input
              type="email"
              className="declaration-text-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              placeholder={question.placeholder || 'email@example.com'}
              onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
            />
            <button
              className="btn-continue declaration-continue"
              onClick={() => submitInputAnswer(question.id)}
              disabled={!declarations[question.id]}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Agent info - combined form with autocomplete
      if (question.type === 'agent_info') {
        const isComplete = agentInfo.name && (agentInfo.phone || agentInfo.email);
        return (
          <div className="declaration-input-container agent-info-form">
            {/* Agent Name with Autocomplete */}
            <div className="form-group agent-search-container">
              <label>Agent Name</label>
              <div className="autocomplete-wrapper">
                <input
                  type="text"
                  className="declaration-text-input fun-input"
                  value={agentSearch || agentInfo.name}
                  onChange={(e) => {
                    const value = e.target.value;
                    setAgentSearch(value);
                    handleAgentInfoChange('name', value);
                    searchRealtors(value);
                  }}
                  onFocus={() => {
                    if (agentSuggestions.length > 0) setShowAgentDropdown(true);
                  }}
                  placeholder="Start typing to search our partner network..."
                />
                {agentLoading && (
                  <span className="autocomplete-loading">Searching...</span>
                )}
                {showAgentDropdown && agentSuggestions.length > 0 && (
                  <div className="autocomplete-dropdown">
                    {agentSuggestions.map((agent) => (
                      <div
                        key={agent.id}
                        className="autocomplete-item"
                        onClick={() => handleSelectAgent(agent)}
                      >
                        <div className="agent-suggestion-name">{agent.name}</div>
                        {agent.company && (
                          <div className="agent-suggestion-company">{agent.company}</div>
                        )}
                      </div>
                    ))}
                    <div
                      className="autocomplete-item manual-entry"
                      onClick={() => setShowAgentDropdown(false)}
                    >
                      <span>Enter details manually</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Company (auto-filled or manual) */}
            <div className="form-group">
              <label>Company / Brokerage</label>
              <input
                type="text"
                className="declaration-text-input fun-input"
                value={agentInfo.company}
                onChange={(e) => handleAgentInfoChange('company', e.target.value)}
                placeholder="Agent's company or brokerage"
              />
            </div>

            {/* Agent Phone */}
            <div className="form-group">
              <label>Agent Phone</label>
              <input
                type="tel"
                className="declaration-text-input fun-input"
                value={agentInfo.phone}
                onChange={(e) => handleAgentInfoChange('phone', e.target.value)}
                placeholder="(555) 555-5555"
              />
            </div>

            {/* Agent Email */}
            <div className="form-group">
              <label>Agent Email</label>
              <input
                type="email"
                className="declaration-text-input fun-input"
                value={agentInfo.email}
                onChange={(e) => handleAgentInfoChange('email', e.target.value)}
                placeholder="agent@example.com"
              />
            </div>

            {agentInfo.partnerId && (
              <div className="partner-badge">
                <Icon name="check" size={16} /> Found in our partner network
              </div>
            )}

            <button
              className="btn-continue declaration-continue"
              onClick={() => handleDeclarationAnswer('agent_info', 'completed')}
              disabled={!isComplete}
            >
              Continue →
            </button>
          </div>
        );
      }

      // Default: choice type
      if (!question.options) {
        return <div className="declaration-options">No options available</div>;
      }
      return (
        <div className="declaration-options">
          {question.options.map(option => (
            <button
              key={option.value}
              className={`declaration-option ${declarations[question.id] === option.value ? 'selected' : ''}`}
              onClick={() => handleDeclarationAnswer(question.id, option.value)}
            >
              <span className="option-icon"><Icon name={option.icon} size={32} /></span>
              <span className="option-label">{option.label}</span>
              {option.description && <span className="option-description">{option.description}</span>}
            </button>
          ))}
        </div>
      );
    };

    return (
      <div className={`declaration-screen ${isAnimating ? 'animating-out' : 'animating-in'}`}>
        <div className="question-number">
          Question {visibleQuestionNum} of {visibleQuestions.length}
        </div>
        <h2 className="declaration-question">{question.question}</h2>
        {question.hint && <p className="declaration-hint"><Icon name="info" size={16} /> {question.hint}</p>}
        {renderQuestionInput()}

        {currentQuestionIndex > 0 && (
          <button className="back-link" onClick={goToPrevQuestion}>
            ← Go back
          </button>
        )}
      </div>
    );
  };

  // Render profile - supports multiple borrowers
  const renderProfileStage = () => {
    const isCollectingCoBorrower = currentBorrower === 2;
    const borrowerData = isCollectingCoBorrower ? coBorrowerData : profileData;
    const setBorrowerData = isCollectingCoBorrower ? setCoBorrowerData : setProfileData;
    const currentSsnDisplay = isCollectingCoBorrower ? coBorrowerSsnDisplay : ssnDisplay;
    const currentSsnRaw = isCollectingCoBorrower ? coBorrowerSsnRaw : ssnRaw;

    // Render borrower form (reusable for both primary and co-borrower)
    const renderBorrowerForm = () => (
      <div className="form-card">
        {hasMultipleBorrowers && (
          <div className="borrower-indicator">
            <span className="borrower-badge">
              <Icon name="user" size={16} />
              {isCollectingCoBorrower ? 'Co-Borrower Information' : 'Primary Borrower Information'}
            </span>
            <span className="borrower-progress">
              Borrower {currentBorrower} of {getBorrowerCount()}
            </span>
          </div>
        )}
        <div className="form-row">
          <div className="form-group">
            <label>First Name</label>
            <input
              type="text"
              value={borrowerData.firstName || ''}
              onChange={(e) => setBorrowerData(prev => ({ ...prev, firstName: e.target.value }))}
              placeholder={isCollectingCoBorrower ? "Co-borrower's first name" : "Your first name"}
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Last Name</label>
            <input
              type="text"
              value={borrowerData.lastName || ''}
              onChange={(e) => setBorrowerData(prev => ({ ...prev, lastName: e.target.value }))}
              placeholder={isCollectingCoBorrower ? "Co-borrower's last name" : "Your last name"}
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={borrowerData.email || ''}
              onChange={(e) => setBorrowerData(prev => ({ ...prev, email: e.target.value }))}
              placeholder="email@example.com"
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={borrowerData.phone || ''}
              onChange={(e) => setBorrowerData(prev => ({ ...prev, phone: e.target.value }))}
              placeholder="(555) 123-4567"
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Date of Birth</label>
            <input
              type="date"
              value={borrowerData.dob || ''}
              onChange={(e) => setBorrowerData(prev => ({ ...prev, dob: e.target.value }))}
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Social Security Number</label>
            <input
              type="text"
              value={currentSsnDisplay}
              onChange={(e) => {
                const newVal = e.target.value;
                if (newVal.length < currentSsnDisplay.length) {
                  const newRaw = currentSsnRaw.slice(0, -1);
                  handleSsnChange(newRaw, isCollectingCoBorrower);
                } else {
                  const lastChar = newVal.slice(-1);
                  if (/\d/.test(lastChar)) {
                    handleSsnChange(currentSsnRaw + lastChar, isCollectingCoBorrower);
                  }
                }
              }}
              placeholder="XXX-XX-1234"
              className="fun-input ssn-input"
              maxLength={11}
              autoComplete="off"
            />
            <span className="input-hint">Only the last 4 digits will be visible</span>
          </div>
        </div>
        {/* Residence History Section */}
        <div className="residence-history-section">
          {(isCollectingCoBorrower ? coBorrowerResidenceHistory : residenceHistory).map((address, index) => (
            <div key={index} className="residence-address-card">
              <div className="residence-header">
                <h4>{index === 0 ? '🏠 Current Address' : `📍 Previous Address ${index}`}</h4>
                {index > 0 && (
                  <button
                    type="button"
                    className="btn-remove-address"
                    onClick={() => removeResidenceAddress(index, isCollectingCoBorrower)}
                  >
                    ✕ Remove
                  </button>
                )}
              </div>
              <div className="form-group">
                <label>Street Address</label>
                <input
                  type="text"
                  value={address.street || ''}
                  onChange={(e) => updateResidenceAddress(index, 'street', e.target.value, isCollectingCoBorrower)}
                  placeholder="123 Main Street, Apt 4B"
                  className="fun-input"
                />
              </div>
              <div className="form-row form-row-3">
                <div className="form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={address.city || ''}
                    onChange={(e) => updateResidenceAddress(index, 'city', e.target.value, isCollectingCoBorrower)}
                    placeholder="City"
                    className="fun-input"
                  />
                </div>
                <div className="form-group">
                  <label>State</label>
                  <select
                    value={address.state || ''}
                    onChange={(e) => updateResidenceAddress(index, 'state', e.target.value, isCollectingCoBorrower)}
                    className="fun-input"
                  >
                    {US_STATES.map(s => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>ZIP Code</label>
                  <input
                    type="text"
                    value={address.zip || ''}
                    onChange={(e) => updateResidenceAddress(index, 'zip', e.target.value.replace(/\D/g, '').slice(0, 5), isCollectingCoBorrower)}
                    placeholder="12345"
                    className="fun-input"
                    maxLength={5}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>How long at this address?</label>
                  <div className="duration-inputs">
                    <div className="duration-field">
                      <input
                        type="number"
                        min="0"
                        max="99"
                        value={address.years || ''}
                        onChange={(e) => updateResidenceAddress(index, 'years', e.target.value, isCollectingCoBorrower)}
                        placeholder="0"
                        className="fun-input duration-input"
                      />
                      <span className="duration-label">Years</span>
                    </div>
                    <div className="duration-field">
                      <input
                        type="number"
                        min="0"
                        max="11"
                        value={address.months || ''}
                        onChange={(e) => updateResidenceAddress(index, 'months', e.target.value, isCollectingCoBorrower)}
                        placeholder="0"
                        className="fun-input duration-input"
                      />
                      <span className="duration-label">Months</span>
                    </div>
                  </div>
                </div>
                <div className="form-group">
                  <label>Housing Status</label>
                  <select
                    value={address.housingStatus || ''}
                    onChange={(e) => updateResidenceAddress(index, 'housingStatus', e.target.value, isCollectingCoBorrower)}
                    className="fun-input"
                  >
                    <option value="">Select...</option>
                    <option value="own">Own</option>
                    <option value="rent">Rent</option>
                    <option value="living_rent_free">Living Rent Free</option>
                  </select>
                </div>
              </div>
            </div>
          ))}

          {/* Residence History Progress */}
          {(() => {
            const currentHistory = isCollectingCoBorrower ? coBorrowerResidenceHistory : residenceHistory;
            const totalMonths = calculateTotalResidenceMonths(currentHistory);
            const needsMore = totalMonths < 24;
            const progressPercent = Math.min((totalMonths / 24) * 100, 100);

            return (
              <div className="residence-progress">
                <div className="residence-progress-bar">
                  <div
                    className="residence-progress-fill"
                    style={{ width: `${progressPercent}%`, backgroundColor: needsMore ? '#f59e0b' : '#10b981' }}
                  />
                </div>
                <div className="residence-progress-text">
                  {needsMore ? (
                    <>
                      <span className="warning-text">⚠️ We need 2 years of residence history</span>
                      <span className="progress-detail">
                        {Math.floor(totalMonths / 12)} year{Math.floor(totalMonths / 12) !== 1 ? 's' : ''}, {totalMonths % 12} month{totalMonths % 12 !== 1 ? 's' : ''} provided
                        — need {24 - totalMonths} more month{24 - totalMonths !== 1 ? 's' : ''}
                      </span>
                    </>
                  ) : (
                    <span className="success-text">✓ 2-year residence history complete</span>
                  )}
                </div>
                {needsMore && (
                  <button
                    type="button"
                    className="btn-add-address"
                    onClick={() => addResidenceAddress(isCollectingCoBorrower)}
                  >
                    + Add Previous Address
                  </button>
                )}
              </div>
            );
          })()}
        </div>
        {!isCollectingCoBorrower && declarations.marital_status === 'married' && (
          <div className="spouse-section">
            <h3><Icon name="users" size={20} /> Spouse Information</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Spouse's First Name</label>
                <input
                  type="text"
                  value={profileData.spouseFirstName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseFirstName: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Spouse's Last Name</label>
                <input
                  type="text"
                  value={profileData.spouseLastName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseLastName: e.target.value }))}
                  className="fun-input"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    );

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>{isCollectingCoBorrower ? `${coBorrowerData.firstName || "Co-Borrower"}'s Information` : "Let's get to know you"}</h2>
          <p>{isCollectingCoBorrower
            ? `Please enter ${coBorrowerData.firstName || "the co-borrower"}'s information`
            : "This should take about 2 minutes"}</p>
        </div>

        {/* Multiple Borrower Process Disclaimer - shown only for primary borrower when multiple borrowers selected */}
        {hasMultipleBorrowers && !isCollectingCoBorrower && (
          <div className="multiple-borrower-disclaimer" style={{
            background: 'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)',
            border: '1px solid #3b82f6',
            borderRadius: '12px',
            padding: '16px 20px',
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px'
          }}>
            <Icon name="users" size={24} style={{ color: '#2563eb', flexShrink: 0, marginTop: '2px' }} />
            <div>
              <p style={{ margin: 0, color: '#1e40af', fontWeight: 600, fontSize: '15px', marginBottom: '6px' }}>
                Multiple Borrowers Detected
              </p>
              <p style={{ margin: 0, color: '#1e3a8a', fontSize: '13px', lineHeight: '1.6' }}>
                Since there are multiple people on this loan application, we'll collect information for each borrower separately.
                We'll start with you (the primary borrower), and once your section is complete, you'll proceed to enter information
                for the co-borrower. Each person's information will be clearly labeled throughout the process.
              </p>
            </div>
          </div>
        )}

        {renderBorrowerForm()}
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => {
            if (isCollectingCoBorrower) {
              setCurrentBorrower(1);
            } else {
              goToPrevStage();
            }
          }}>← Back</button>

          {/* Show "Add Co-Borrower" button if primary borrower done and multiple borrowers selected */}
          {!isCollectingCoBorrower && hasMultipleBorrowers && currentBorrower === 1 ? (
            <button
              className="btn-continue btn-add-coborrower"
              onClick={() => setCurrentBorrower(2)}
            >
              Add Co-Borrower →
            </button>
          ) : (
            <button className="btn-continue" onClick={() => {
              if (isCollectingCoBorrower) {
                // Done with co-borrower, go to next stage
                goToNextStage();
              } else if (hasMultipleBorrowers) {
                // Primary done, need co-borrower
                setCurrentBorrower(2);
              } else {
                goToNextStage();
              }
            }}>Continue →</button>
          )}
        </div>
      </div>
    );
  };

  // Render income
  const renderIncomeStage = () => {
    const isCollectingCoBorrowerIncome = currentIncomeBorrower === 2;
    const currentIncomeDataState = isCollectingCoBorrowerIncome ? coBorrowerIncomeData : incomeData;
    const setCurrentIncomeData = isCollectingCoBorrowerIncome ? setCoBorrowerIncomeData : setIncomeData;

    // Get borrower names for display
    const primaryBorrowerName = profileData?.firstName || 'Primary Borrower';
    const coBorrowerName = coBorrowerData?.firstName || 'Co-Borrower';
    const currentBorrowerName = isCollectingCoBorrowerIncome ? coBorrowerName : primaryBorrowerName;

    const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';

    // Determine income type from declarations (for primary) or assume employed for co-borrower
    const getIncomeType = () => {
      if (isCollectingCoBorrowerIncome) {
        // For co-borrower, check their income type or default to employed
        return coBorrowerIncomeData.incomeType || 'employed';
      }
      if (declarations.self_employed === 'yes') return 'self_employed';
      if (declarations.self_employed === 'side_business') return 'employed_with_business';
      return 'employed'; // Default to employed if 'no' or not set
    };

    const currentIncomeType = getIncomeType();

    // Show income details directly (skip the duplicate question)
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>
            {isCollectingCoBorrowerIncome
              ? `${coBorrowerName}'s Employment Details`
              : (currentIncomeType === 'employed' && `${primaryBorrowerName}'s Employment Details`) ||
                (currentIncomeType === 'self_employed' && `${primaryBorrowerName}'s Business Details`) ||
                (currentIncomeType === 'employed_with_business' && `${primaryBorrowerName}'s Employment & Business Details`)
            }
          </h2>
          <p>{isCollectingCoBorrowerIncome
            ? `Tell us about ${coBorrowerName}'s income`
            : 'Tell us more about your income'}</p>
        </div>

        {/* Borrower indicator for multiple borrowers */}
        {hasMultipleBorrowers && (
          <div className="borrower-income-indicator" style={{
            background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
            border: '1px solid #22c55e',
            borderRadius: '12px',
            padding: '12px 16px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Icon name="income" size={20} style={{ color: '#16a34a' }} />
              <span style={{ color: '#166534', fontWeight: 600, fontSize: '14px' }}>
                {isCollectingCoBorrowerIncome
                  ? `Collecting ${coBorrowerName}'s income information`
                  : `Collecting ${primaryBorrowerName}'s income information`
                }
              </span>
            </div>
            <span style={{
              background: '#22c55e',
              color: 'white',
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: 600
            }}>
              Borrower {currentIncomeBorrower} of {getBorrowerCount()}
            </span>
          </div>
        )}

        {/* Co-borrower income type selection (only for co-borrower) */}
        {isCollectingCoBorrowerIncome && !currentIncomeDataState.incomeType && (
          <div className="form-card" style={{ marginBottom: '20px' }}>
            <h3 style={{ marginBottom: '16px' }}>How does {coBorrowerName} earn income?</h3>
            <div className="income-type-selection" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <button
                className={`income-type-btn ${currentIncomeDataState.incomeType === 'employed' ? 'selected' : ''}`}
                onClick={() => setCurrentIncomeData(prev => ({ ...prev, incomeType: 'employed' }))}
                style={{
                  padding: '16px 24px',
                  border: '2px solid #e5e7eb',
                  borderRadius: '12px',
                  background: currentIncomeDataState.incomeType === 'employed' ? '#0d9488' : 'white',
                  color: currentIncomeDataState.incomeType === 'employed' ? 'white' : '#374151',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500
                }}
              >
                W-2 Employee
              </button>
              <button
                className={`income-type-btn ${currentIncomeDataState.incomeType === 'self_employed' ? 'selected' : ''}`}
                onClick={() => setCurrentIncomeData(prev => ({ ...prev, incomeType: 'self_employed' }))}
                style={{
                  padding: '16px 24px',
                  border: '2px solid #e5e7eb',
                  borderRadius: '12px',
                  background: currentIncomeDataState.incomeType === 'self_employed' ? '#0d9488' : 'white',
                  color: currentIncomeDataState.incomeType === 'self_employed' ? 'white' : '#374151',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500
                }}
              >
                Self-Employed
              </button>
            </div>
          </div>
        )}

        {/* Employment form - show for W-2 employees or primary borrower employed types */}
        {((currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') ||
          (isCollectingCoBorrowerIncome && currentIncomeDataState.incomeType === 'employed')) && (
          <div className="form-card">
            <EmployerAutocomplete
              value={currentIncomeDataState.employerName || ''}
              onChange={(value) => setCurrentIncomeData(prev => ({ ...prev, employerName: value }))}
              onEmployerSelect={(employer) => {
                setCurrentIncomeData(prev => ({
                  ...prev,
                  employerName: employer.name,
                  employerAddress: employer.address,
                  employerCity: employer.city,
                  employerState: employer.state,
                  employerPhone: employer.phone,
                }));
              }}
              label={`${currentBorrowerName}'s Employer Name`}
              placeholder="Start typing company name..."
              className="fun-input-wrapper"
            />
            <div className="form-group">
              <label>Employer Address</label>
              <input
                type="text"
                value={currentIncomeDataState.employerAddress || ''}
                onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employerAddress: e.target.value }))}
                className="fun-input"
                placeholder="Auto-filled from employer selection"
              />
            </div>
            <div className="form-group">
              <label>Employer Phone</label>
              <input
                type="tel"
                value={currentIncomeDataState.employerPhone || ''}
                onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employerPhone: e.target.value }))}
                className="fun-input"
                placeholder="Auto-filled from employer selection"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Job Title</label>
                <input
                  type="text"
                  value={currentIncomeDataState.jobTitle || ''}
                  onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, jobTitle: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Start Date</label>
                <input
                  type="month"
                  value={currentIncomeDataState.employmentStartDate || ''}
                  onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employmentStartDate: e.target.value }))}
                  className="fun-input"
                  max={new Date().toISOString().slice(0, 7)}
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Base Salary</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={currentIncomeDataState.annualSalary || ''}
                  onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, annualSalary: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        )}

        {/* Previous Employer - shown if less than 2 years at current job */}
        {(currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') &&
         incomeData.employmentStartDate && (() => {
           const startDate = new Date(incomeData.employmentStartDate + '-01');
           const twoYearsAgo = new Date();
           twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);
           return startDate > twoYearsAgo;
         })() && (
          <div className="form-card">
            <h3>Previous Employer</h3>
            <p className="section-hint">Since you've been at your current job less than 2 years, we need your previous employment history.</p>
            <div className="form-group">
              <label>Previous Employer Name</label>
              <input
                type="text"
                value={incomeData.prevEmployerName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmployerName: e.target.value }))}
                className="fun-input"
                placeholder="Previous company name"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Job Title</label>
                <input
                  type="text"
                  value={incomeData.prevJobTitle || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, prevJobTitle: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Start Date</label>
                <input
                  type="month"
                  value={incomeData.prevEmploymentStartDate || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmploymentStartDate: e.target.value }))}
                  className="fun-input"
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>End Date</label>
                <input
                  type="month"
                  value={incomeData.prevEmploymentEndDate || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmploymentEndDate: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Annual Salary (at that job)</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={incomeData.prevAnnualSalary || ''}
                    onChange={(e) => setIncomeData(prev => ({ ...prev, prevAnnualSalary: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Second Job Question */}
        {(currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') && (
          <div className="form-card">
            <h3>Do you have a second job?</h3>
            <div className="yes-no-buttons">
              <button
                type="button"
                className={`yes-no-btn ${incomeData.hasSecondJob === 'yes' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, hasSecondJob: 'yes' }))}
              >
                Yes
              </button>
              <button
                type="button"
                className={`yes-no-btn ${incomeData.hasSecondJob === 'no' ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, hasSecondJob: 'no' }))}
              >
                No
              </button>
            </div>
          </div>
        )}

        {/* Second Job Details */}
        {incomeData.hasSecondJob === 'yes' && (
          <div className="form-card">
            <h3>Second Job Details</h3>
            <div className="form-group">
              <label>Employer Name</label>
              <input
                type="text"
                value={incomeData.secondEmployerName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, secondEmployerName: e.target.value }))}
                className="fun-input"
                placeholder="Second employer name"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Job Title</label>
                <input
                  type="text"
                  value={incomeData.secondJobTitle || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, secondJobTitle: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Start Date</label>
                <input
                  type="month"
                  value={incomeData.secondEmploymentStartDate || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, secondEmploymentStartDate: e.target.value }))}
                  className="fun-input"
                  max={new Date().toISOString().slice(0, 7)}
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Income (from second job)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.secondJobIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, secondJobIncome: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        )}

        {(currentIncomeType === 'self_employed' || currentIncomeType === 'employed_with_business') && (
          <div className="form-card">
            <div className="form-group">
              <label>Business Name</label>
              <input
                type="text"
                value={incomeData.businessName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, businessName: e.target.value }))}
                className="fun-input"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Business Type</label>
                <select
                  value={incomeData.businessType || ''}
                  onChange={(e) => handleIncomeFieldChange('businessType', e.target.value, setIncomeData)}
                  className="fun-input"
                >
                  <option value="">Select...</option>
                  <option value="sole_prop">Sole Proprietorship</option>
                  <option value="llc">LLC</option>
                  <option value="s_corp">S-Corporation</option>
                  <option value="c_corp">C-Corporation</option>
                </select>
              </div>
              <div className="form-group">
                <label>Ownership %</label>
                <input
                  type="number"
                  value={incomeData.ownershipPercent || ''}
                  onChange={(e) => handleIncomeFieldChange('ownershipPercent', e.target.value, setIncomeData)}
                  className="fun-input"
                  min="0"
                  max="100"
                  placeholder="25"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Net Income (from business)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.businessIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessIncome: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <span className="input-hint">Use your net income from Schedule C or K-1</span>
            </div>
          </div>
        )}

        {/* Additional income section for rental, retirement, etc. */}
        <div className="form-card">
          <h3>Additional Income (Optional)</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Monthly Rental Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.rentalIncome || ''}
                  onChange={(e) => handleIncomeFieldChange('rentalIncome', e.target.value, setIncomeData)}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Other Monthly Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.otherIncome || ''}
                  onChange={(e) => handleIncomeFieldChange('otherIncome', e.target.value, setIncomeData)}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => {
            if (isCollectingCoBorrowerIncome) {
              // Go back to primary borrower income
              setCurrentIncomeBorrower(1);
            } else {
              goToPrevStage();
            }
          }}>← Back</button>

          {/* Show appropriate continue button based on multiple borrower state */}
          {!isCollectingCoBorrowerIncome && hasMultipleBorrowers ? (
            <button
              className="btn-continue"
              onClick={() => setCurrentIncomeBorrower(2)}
            >
              Continue to {coBorrowerName}'s Income →
            </button>
          ) : (
            <button className="btn-continue" onClick={() => {
              if (isCollectingCoBorrowerIncome) {
                // Done with co-borrower income, reset and go to next stage
                setCurrentIncomeBorrower(1);
              }
              goToNextStage();
            }}>Continue →</button>
          )}
        </div>
      </div>
    );
  };

  // Render assets
  const renderAssetsStage = () => {
    const hasGiftFunds = declarations.gift_funds === 'yes';

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your Down Payment Funds</h2>
          <p>Let's see what you have saved for your new home</p>
        </div>
        <div className="form-card">
          <div className="form-row">
            <div className="form-group">
              <label>Checking Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.checking || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, checking: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Savings Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.savings || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, savings: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Investment Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.investments || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, investments: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Retirement (401k, IRA)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.retirement || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, retirement: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          {hasGiftFunds && (
            <div className="gift-funds-section">
              <h3><Icon name="gift" size={20} /> Gift Funds Details</h3>
              <p className="section-hint">Great news! Gift funds can help with your down payment.</p>
              <div className="form-group">
                <label>Gift Amount</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={assetData.giftAmount || ''}
                    onChange={(e) => handleAssetFieldChange('giftAmount', e.target.value, setAssetData)}
                    className="fun-input"
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Donor Name</label>
                  <input
                    type="text"
                    value={assetData.donorName || ''}
                    onChange={(e) => handleAssetFieldChange('donorName', e.target.value, setAssetData)}
                    className="fun-input"
                    placeholder="Who is giving the gift?"
                  />
                </div>
                <div className="form-group">
                  <label>Relationship</label>
                  <select
                    value={assetData.donorRelationship || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, donorRelationship: e.target.value }))}
                    className="fun-input"
                  >
                    <option value="">Select...</option>
                    <option value="parent">Parent</option>
                    <option value="grandparent">Grandparent</option>
                    <option value="sibling">Sibling</option>
                    <option value="other_family">Other Family</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="total-assets-display">
          <span>Total Available for Down Payment:</span>
          <strong>
            ${(
              (parseFloat(assetData.checking) || 0) +
              (parseFloat(assetData.savings) || 0) +
              (parseFloat(assetData.investments) || 0) +
              (parseFloat(assetData.giftAmount) || 0)
            ).toLocaleString()}
          </strong>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render property (purchase-specific)
  const renderPropertyStage = () => {
    const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
    const isFirstTimeBuyer = declarations.first_time_buyer === 'yes';

    // Step 1: Property Type and Occupancy
    if (propertyStep === 1) {
      return (
        <div className="stage-content">
          <div className="stage-header">
            <h2>Property Type</h2>
            <p>What type of property are you looking for?</p>
          </div>

          <div className="form-card">
            <div className="property-type-selector">
              <div className="income-cards">
                <div
                  className={`income-card ${propertyData.propertyType === 'Single Family' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, propertyType: 'Single Family' }))}
                >
                  <span className="card-icon"><Icon name="home" size={28} /></span>
                  <span className="card-label">Single Family</span>
                  <span className="card-desc">Detached home</span>
                </div>
                <div
                  className={`income-card ${propertyData.propertyType === 'Condo' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, propertyType: 'Condo' }))}
                >
                  <span className="card-icon"><Icon name="building" size={28} /></span>
                  <span className="card-label">Condo</span>
                  <span className="card-desc">Condominium unit</span>
                </div>
                <div
                  className={`income-card ${propertyData.propertyType === 'Townhouse' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, propertyType: 'Townhouse' }))}
                >
                  <span className="card-icon"><Icon name="layers" size={28} /></span>
                  <span className="card-label">Townhouse</span>
                  <span className="card-desc">Attached home</span>
                </div>
                <div
                  className={`income-card ${propertyData.propertyType === 'Multi-Family' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, propertyType: 'Multi-Family' }))}
                >
                  <span className="card-icon"><Icon name="users" size={28} /></span>
                  <span className="card-label">Multi-Family</span>
                  <span className="card-desc">2-4 units</span>
                </div>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
            <button
              className="btn-continue"
              onClick={() => setPropertyStep(2)}
              disabled={!propertyData.propertyType}
            >
              Continue →
            </button>
          </div>
        </div>
      );
    }

    // Step 2: Occupancy Type
    if (propertyStep === 2) {
      return (
        <div className="stage-content">
          <div className="stage-header">
            <h2>How Will You Use This Home?</h2>
            <p>This affects your loan options and rates</p>
          </div>

          <div className="form-card">
            <div className="occupancy-selector">
              <div className="income-cards">
                <div
                  className={`income-card ${propertyData.occupancy === 'primary' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'primary' }))}
                >
                  <span className="card-icon"><Icon name="home" size={28} /></span>
                  <span className="card-label">Primary Home</span>
                  <span className="card-desc">I'll live here</span>
                </div>
                <div
                  className={`income-card ${propertyData.occupancy === 'second' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'second' }))}
                >
                  <span className="card-icon"><Icon name="beach" size={28} /></span>
                  <span className="card-label">Second Home</span>
                  <span className="card-desc">Vacation property</span>
                </div>
                <div
                  className={`income-card ${propertyData.occupancy === 'investment' ? 'selected' : ''}`}
                  onClick={() => setPropertyData(prev => ({ ...prev, occupancy: 'investment' }))}
                >
                  <span className="card-icon"><Icon name="trendUp" size={28} /></span>
                  <span className="card-label">Investment</span>
                  <span className="card-desc">Rental income</span>
                </div>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPropertyStep(1)}>← Back</button>
            <button
              className="btn-continue"
              onClick={() => setPropertyStep(3)}
              disabled={!propertyData.occupancy}
            >
              Continue →
            </button>
          </div>
        </div>
      );
    }

    // Step 3: Price, Down Payment, and Loan Program
    // Pre-fill from payment calculator if available
    const prefilledPrice = paymentEstimate?.homeValue || propertyData.purchasePrice;
    const prefilledDownPayment = paymentEstimate?.downPaymentAmount || propertyData.downPayment;

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Estimated Budget & Loan Details</h2>
          <p>Review your preliminary numbers below</p>
        </div>

        {/* Preliminary Numbers Disclaimer */}
        <div className="preliminary-disclaimer" style={{
          background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
          border: '1px solid #f59e0b',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px'
        }}>
          <Icon name="info" size={20} style={{ color: '#d97706', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <p style={{ margin: 0, color: '#92400e', fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
              Preliminary Estimates
            </p>
            <p style={{ margin: 0, color: '#78350f', fontSize: '13px', lineHeight: '1.5' }}>
              The numbers shown below are estimates based on the information you've provided. Your loan officer will review these details with you and make any necessary adjustments based on current rates, your specific situation, and available loan programs.
            </p>
          </div>
        </div>

        {/* Budget Summary from Payment Calculator */}
        {paymentEstimate && (
          <div className="form-card budget-summary-card">
            <div className="budget-summary-header">
              <Icon name="calculator" size={24} />
              <h3>Your Budget Summary</h3>
              <button
                className="edit-button"
                onClick={() => setCurrentStage('goals')}
                style={{
                  marginLeft: 'auto',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  background: 'transparent',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  color: '#374151',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = '#f3f4f6';
                  e.target.style.borderColor = '#d1d5db';
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'transparent';
                  e.target.style.borderColor = '#e5e7eb';
                }}
              >
                <Icon name="edit" size={16} />
                Edit
              </button>
            </div>
            <div className="budget-summary-grid">
              <div className="budget-item">
                <span className="budget-label">Home Value</span>
                <span className="budget-value">${paymentEstimate.homeValue?.toLocaleString()}</span>
              </div>
              <div className="budget-item">
                <span className="budget-label">Down Payment</span>
                <span className="budget-value">${paymentEstimate.downPaymentAmount?.toLocaleString()} ({paymentEstimate.downPaymentPercent}%)</span>
              </div>
              <div className="budget-item">
                <span className="budget-label">Loan Amount</span>
                <span className="budget-value">${paymentEstimate.loanAmount?.toLocaleString()}</span>
              </div>
              <div className="budget-item highlight">
                <span className="budget-label">Est. Monthly Payment</span>
                <span className="budget-value">${paymentEstimate.payment?.totalMonthly?.toLocaleString()}</span>
              </div>
            </div>
            <div className="budget-breakdown">
              <div className="breakdown-row">
                <span>Principal & Interest</span>
                <span>${paymentEstimate.payment?.principalAndInterest?.toLocaleString()}</span>
              </div>
              <div className="breakdown-row">
                <span>Property Tax</span>
                <span>${paymentEstimate.payment?.propertyTax?.toLocaleString()}/mo</span>
              </div>
              <div className="breakdown-row">
                <span>Insurance</span>
                <span>${paymentEstimate.payment?.homeownersInsurance?.toLocaleString()}/mo</span>
              </div>
              {paymentEstimate.payment?.pmi > 0 && (
                <div className="breakdown-row">
                  <span>Mortgage Insurance</span>
                  <span>${paymentEstimate.payment?.pmi?.toLocaleString()}/mo</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Only show this form card if there's something to display */}
        {(declarations.found_property === 'yes' || !paymentEstimate) && (
          <div className="form-card">
            {declarations.found_property === 'yes' && (
              <AddressAutocomplete
                value={propertyData.address || ''}
                onChange={(value) => setPropertyData(prev => ({ ...prev, address: value }))}
                onAddressSelect={(addressData) => {
                  setPropertyData(prev => ({
                    ...prev,
                    address: addressData.formatted,
                    street: addressData.street,
                    city: addressData.city,
                    state: addressData.state_code,
                    zip: addressData.zip,
                    county: addressData.county,
                  }));
                }}
                label="Property Address"
                placeholder="Enter property address..."
                className="fun-input-wrapper"
              />
            )}

            {/* Only show manual price/down payment inputs when no budget summary exists */}
            {!paymentEstimate && (
              <div className="form-row">
                <div className="form-group">
                  <label>{declarations.found_property === 'yes' ? 'Purchase Price' : 'Target Price Range'}</label>
                  <div className="input-with-prefix">
                    <span className="input-prefix">$</span>
                    <input
                      type="number"
                      value={propertyData.purchasePrice || prefilledPrice || ''}
                      onChange={(e) => setPropertyData(prev => ({ ...prev, purchasePrice: e.target.value }))}
                      className="fun-input"
                      placeholder="0"
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Down Payment</label>
                  <div className="input-with-prefix">
                    <span className="input-prefix">$</span>
                    <input
                      type="number"
                      value={propertyData.downPayment || prefilledDownPayment || ''}
                      onChange={(e) => setPropertyData(prev => ({ ...prev, downPayment: e.target.value }))}
                      className="fun-input"
                      placeholder="0"
                    />
                  </div>
                  {(propertyData.purchasePrice || prefilledPrice) && (propertyData.downPayment || prefilledDownPayment) && (
                    <span className="calculated-hint">
                      {(((propertyData.downPayment || prefilledDownPayment) / (propertyData.purchasePrice || prefilledPrice)) * 100).toFixed(1)}% down
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Payment Calculator - shows when purchase price is entered and no budget summary exists */}
        {!paymentEstimate && (propertyData.purchasePrice || prefilledPrice) && parseFloat(propertyData.purchasePrice || prefilledPrice) > 0 && (
          <div className="form-card payment-calculator-section">
            <PaymentCalculator
              initialHomeValue={parseFloat(propertyData.purchasePrice || prefilledPrice) || 0}
              initialDownPayment={parseFloat(propertyData.downPayment || prefilledDownPayment) || 0}
              initialState={propertyData.state || ''}
              initialCounty={propertyData.county || ''}
              initialPropertyUse={propertyData.occupancy === 'primary' ? 'primaryResidence' :
                                  propertyData.occupancy === 'second' ? 'secondHome' :
                                  propertyData.occupancy === 'investment' ? 'rental' : 'primaryResidence'}
              showAdvancedOptions={false}
              onCalculationComplete={(calculation) => {
                setPaymentEstimate(calculation);
              }}
            />
          </div>
        )}

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPropertyStep(2)}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render review
  const renderReviewStage = () => {
    // Calculate totals for summary
    const totalAssets = (parseFloat(assetData.checking) || 0) +
      (parseFloat(assetData.savings) || 0) +
      (parseFloat(assetData.investments) || 0) +
      (parseFloat(assetData.giftAmount) || 0);
    // Use paymentEstimate data if available (from Budget Calculator), otherwise fall back to propertyData
    const purchasePrice = paymentEstimate?.homeValue || parseFloat(propertyData.purchasePrice || 0);
    const downPaymentAmount = paymentEstimate?.downPaymentAmount || parseFloat(propertyData.downPayment || 0);
    const loanAmount = paymentEstimate?.loanAmount || (purchasePrice - downPaymentAmount);
    const downPaymentPercent = paymentEstimate?.downPaymentPercent || (purchasePrice > 0 ? ((downPaymentAmount / purchasePrice) * 100).toFixed(1) : 0);

    // Build welcome message with borrower names
    const borrowerNames = [profileData.firstName];
    if (hasMultipleBorrowers && coBorrowerData.firstName) {
      borrowerNames.push(coBorrowerData.firstName);
    }
    const welcomeMessage = `Welcome ${borrowerNames.join(' and ')}`;

    return (
      <div className="stage-content review-stage">
        <div className="stage-header">
          <h2>{welcomeMessage}</h2>
          <p>Almost there! Review your information below and make any edits needed.</p>
        </div>

        {/* Summary Hero Card */}
        <div className="review-hero-card">
          <div className="hero-icon-wrapper">
            <Icon name="check" size={32} />
          </div>
          <div className="hero-content">
            <h3>Your Loan Summary</h3>
            <div className="hero-stats">
              <div className="hero-stat">
                <span className="stat-label">Purchase Price</span>
                <span className="stat-value">${purchasePrice.toLocaleString()}</span>
              </div>
              <div className="hero-stat-divider"></div>
              <div className="hero-stat">
                <span className="stat-label">Down Payment</span>
                <span className="stat-value">${downPaymentAmount.toLocaleString()} <small>({downPaymentPercent}%)</small></span>
              </div>
              <div className="hero-stat-divider"></div>
              <div className="hero-stat">
                <span className="stat-label">Loan Amount</span>
                <span className="stat-value highlight">${loanAmount.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="review-grid">
          {/* Borrower Card - styled like Co-Borrower card */}
          <div className="review-card borrower-card">
            <div className="card-header">
              <div className="card-icon borrower-icon">
                <Icon name="user" size={24} />
              </div>
              <div className="card-title">
                <h4>Borrower Information</h4>
                <span className="card-subtitle">Primary applicant details</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="profile" size={16} />
                <span className="info-label">Full Name</span>
                <span className="info-value">{profileData.firstName} {profileData.lastName}</span>
              </div>
              <div className="info-row">
                <Icon name="email" size={16} />
                <span className="info-label">Email</span>
                <span className="info-value">{profileData.email}</span>
              </div>
              <div className="info-row">
                <Icon name="phone" size={16} />
                <span className="info-label">Phone</span>
                <span className="info-value">{profileData.phone}</span>
              </div>
              {ssnDisplay && (
                <div className="info-row">
                  <Icon name="lock" size={16} />
                  <span className="info-label">SSN</span>
                  <span className="info-value masked">{ssnDisplay}</span>
                </div>
              )}
            </div>
          </div>

          {/* Income Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon income-icon">
                <Icon name="briefcase" size={24} />
              </div>
              <div className="card-title">
                <h4>Employment & Income</h4>
                <span className="card-subtitle">Your income sources</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('income')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="briefcase" size={16} />
                <span className="info-label">Employment Type</span>
                <span className="info-value capitalize">{incomeData.primaryType?.replace('_', ' ') || 'Not specified'}</span>
              </div>
              {incomeData.employerName && (
                <div className="info-row">
                  <Icon name="building" size={16} />
                  <span className="info-label">Employer</span>
                  <span className="info-value">{incomeData.employerName}</span>
                </div>
              )}
              {incomeData.annualSalary && (
                <div className="info-row highlight-row">
                  <Icon name="dollarSign" size={16} />
                  <span className="info-label">Annual Income</span>
                  <span className="info-value">${parseFloat(incomeData.annualSalary).toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>

          {/* Assets Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon assets-icon">
                <Icon name="dollarSign" size={24} />
              </div>
              <div className="card-title">
                <h4>Assets & Down Payment</h4>
                <span className="card-subtitle">Your available funds</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('assets')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              {parseFloat(assetData.checking) > 0 && (
                <div className="info-row">
                  <Icon name="creditCard" size={16} />
                  <span className="info-label">Checking</span>
                  <span className="info-value">${parseFloat(assetData.checking).toLocaleString()}</span>
                </div>
              )}
              {parseFloat(assetData.savings) > 0 && (
                <div className="info-row">
                  <Icon name="piggyBank" size={16} />
                  <span className="info-label">Savings</span>
                  <span className="info-value">${parseFloat(assetData.savings).toLocaleString()}</span>
                </div>
              )}
              {parseFloat(assetData.investments) > 0 && (
                <div className="info-row">
                  <Icon name="chart" size={16} />
                  <span className="info-label">Investments</span>
                  <span className="info-value">${parseFloat(assetData.investments).toLocaleString()}</span>
                </div>
              )}
              {declarations.gift_funds === 'yes' && parseFloat(assetData.giftAmount) > 0 && (
                <div className="info-row">
                  <Icon name="gift" size={16} />
                  <span className="info-label">Gift Funds</span>
                  <span className="info-value">${parseFloat(assetData.giftAmount).toLocaleString()}</span>
                </div>
              )}
              <div className="info-row total-row">
                <Icon name="wallet" size={16} />
                <span className="info-label">Total Available</span>
                <span className="info-value">${totalAssets.toLocaleString()}</span>
              </div>
            </div>
          </div>

          {/* Property Card */}
          <div className="review-card">
            <div className="card-header">
              <div className="card-icon property-icon">
                <Icon name="home" size={24} />
              </div>
              <div className="card-title">
                <h4>Property Details</h4>
                <span className="card-subtitle">Your new home</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('property')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="home" size={16} />
                <span className="info-label">Property Type</span>
                <span className="info-value capitalize">{propertyData.propertyType?.replace('_', ' ') || 'Not specified'}</span>
              </div>
              <div className="info-row">
                <Icon name="mapPin" size={16} />
                <span className="info-label">Location</span>
                <span className="info-value">{propertyData.state || 'Not specified'}{propertyData.county ? `, ${propertyData.county}` : ''}</span>
              </div>
              <div className="info-row">
                <Icon name="document" size={16} />
                <span className="info-label">Loan Program</span>
                <span className="info-value uppercase">{propertyData.program || 'Conventional'}</span>
              </div>
              <div className="info-row">
                <Icon name="calendar" size={16} />
                <span className="info-label">Occupancy</span>
                <span className="info-value capitalize">{propertyData.occupancy?.replace('_', ' ') || 'Primary Residence'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Co-Borrower Section if applicable */}
        {hasMultipleBorrowers && coBorrowerData.firstName && (
          <div className="review-card coborrower-card">
            <div className="card-header">
              <div className="card-icon coborrower-icon">
                <Icon name="users" size={24} />
              </div>
              <div className="card-title">
                <h4>Co-Borrower Information</h4>
                <span className="card-subtitle">Second applicant details</span>
              </div>
              <button className="edit-btn-modern" onClick={() => setCurrentStage('profile')}>
                <Icon name="edit" size={16} />
                <span>Edit</span>
              </button>
            </div>
            <div className="card-body">
              <div className="info-row">
                <Icon name="profile" size={16} />
                <span className="info-label">Full Name</span>
                <span className="info-value">{coBorrowerData.firstName} {coBorrowerData.lastName}</span>
              </div>
              <div className="info-row">
                <Icon name="email" size={16} />
                <span className="info-label">Email</span>
                <span className="info-value">{coBorrowerData.email}</span>
              </div>
              <div className="info-row">
                <Icon name="phone" size={16} />
                <span className="info-label">Phone</span>
                <span className="info-value">{coBorrowerData.phone}</span>
              </div>
              {coBorrowerSsnDisplay && (
                <div className="info-row">
                  <Icon name="lock" size={16} />
                  <span className="info-label">SSN</span>
                  <span className="info-value masked">{coBorrowerSsnDisplay}</span>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Toggle multi-select options for planning
  const togglePlanningOption = (field, value) => {
    setPlanningData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  // Render planning stage with mortgage questionnaire - split into 6 pages
  const renderPlanningStage = () => {
    // Step 1: Payment Calculator - How much do you want to borrow?
    if (planningStep === 1) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Your Monthly Payment Estimate</h2>
            <p>See how your down payment affects your monthly cost. Adjust the values to find your comfort zone.</p>
          </div>

          <div className="form-card planning-section payment-calculator-section">
            <PaymentCalculator
              initialHomeValue={parseFloat(propertyData.purchasePrice) || 0}
              initialDownPayment={parseFloat(propertyData.downPayment) || 0}
              initialState={propertyData.state || ''}
              initialCounty={propertyData.county || ''}
              initialPropertyUse={propertyData.occupancy === 'primary' ? 'primaryResidence' :
                                  propertyData.occupancy === 'second' ? 'secondHome' :
                                  propertyData.occupancy === 'investment' ? 'rental' : 'primaryResidence'}
              showAdvancedOptions={true}
              onCalculationComplete={(calculation) => {
                setPaymentEstimate(calculation);
              }}
            />
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(2)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 2: Mortgage Priorities
    if (planningStep === 2) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>What matters most to you in your mortgage?</h2>
            <p>Select all that apply - this helps us find the best loan options for you.</p>
          </div>

          <div className="form-card planning-section">
            <div className="multi-select-grid">
              {PLANNING_QUESTIONS.mortgagePriorities.options.map(option => (
                <button
                  key={option.value}
                  className={`multi-select-option ${planningData.mortgagePriorities.includes(option.value) ? 'selected' : ''}`}
                  onClick={() => togglePlanningOption('mortgagePriorities', option.value)}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(1)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(3)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 3: Personal Goals
    if (planningStep === 3) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>What are your personal financial goals?</h2>
            <p>Select all that apply - help us align your mortgage with your life plans.</p>
          </div>

          <div className="form-card planning-section">
            <div className="multi-select-grid">
              {PLANNING_QUESTIONS.personalGoals.options.map(option => (
                <button
                  key={option.value}
                  className={`multi-select-option ${planningData.personalGoals.includes(option.value) ? 'selected' : ''}`}
                  onClick={() => togglePlanningOption('personalGoals', option.value)}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(2)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(4)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 4: Financial Philosophy
    if (planningStep === 4) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>How would you describe your financial approach?</h2>
            <p>This helps us recommend the right loan structure for your style.</p>
          </div>

          <div className="form-card planning-section">
            <div className="philosophy-options">
              {PLANNING_QUESTIONS.financialPhilosophy.options.map(option => (
                <button
                  key={option.value}
                  className={`philosophy-option ${planningData.financialPhilosophy === option.value ? 'selected' : ''}`}
                  onClick={() => setPlanningData(prev => ({ ...prev, financialPhilosophy: option.value }))}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                  <span className="option-description">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(3)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(5)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 5: Tax-Deferred Retirement
    if (planningStep === 5) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Are you currently contributing to a tax-deferred retirement account?</h2>
            <p>We can coordinate with your existing team for a comprehensive financial plan.</p>
          </div>

          <div className="form-card planning-section">
            <div className="single-select-options">
              {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
                <button
                  key={option.value}
                  className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`}
                  onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(4)}>← Back</button>
            <button className="btn-continue" onClick={() => setPlanningStep(6)}>Continue →</button>
          </div>
        </div>
      );
    }

    // Step 6: Professional Network - with substeps for follow-up questions
    const selectedProfessionals = planningData.professionalNetwork || [];
    const professionalLabels = {
      financial_planner: 'Financial Planner',
      accountant: 'CPA / Accountant',
      insurance_agent: 'Life Insurance Agent',
      estate_planner: 'Estate Planner'
    };

    // Substep 1: Select professionals
    if (professionalSubStep === 1) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Do you currently work with any of these professionals?</h2>
            <p>We can coordinate with your existing team for a comprehensive financial plan.</p>
          </div>

          <div className="form-card planning-section">
            <div className="multi-select-grid compact">
              {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
                <button
                  key={option.value}
                  className={`multi-select-option ${selectedProfessionals.includes(option.value) ? 'selected' : ''}`}
                  onClick={() => togglePlanningOption('professionalNetwork', option.value)}
                >
                  <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                  <span className="option-label">{option.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setPlanningStep(5)}>← Back</button>
            <button className="btn-continue" onClick={() => {
              if (selectedProfessionals.length > 0) {
                setProfessionalSubStep(2); // Ask if they want them involved
              } else {
                setProfessionalSubStep(4); // Ask if they want introductions
              }
            }}>Continue →</button>
          </div>
        </div>
      );
    }

    // Substep 2: Ask if they want professionals involved in decision making
    if (professionalSubStep === 2 && selectedProfessionals.length > 0) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Would you like your professionals involved in the decision-making process?</h2>
            <p>We can keep them informed and coordinate for a seamless experience.</p>
          </div>

          <div className="form-card planning-section">
            <div className="single-select-options">
              <button
                className={`single-select-option ${wantProfessionalsInvolved === true ? 'selected' : ''}`}
                onClick={() => setWantProfessionalsInvolved(true)}
              >
                <span className="option-icon"><Icon name="check" size={32} /></span>
                <span className="option-label">Yes, please involve them</span>
              </button>
              <button
                className={`single-select-option ${wantProfessionalsInvolved === false ? 'selected' : ''}`}
                onClick={() => setWantProfessionalsInvolved(false)}
              >
                <span className="option-icon"><Icon name="x" size={32} /></span>
                <span className="option-label">No, not at this time</span>
              </button>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setProfessionalSubStep(1)}>← Back</button>
            <button
              className="btn-continue"
              disabled={wantProfessionalsInvolved === null}
              onClick={() => {
                if (wantProfessionalsInvolved) {
                  setProfessionalSubStep(3); // Get contact info
                } else {
                  setPlanningStep(1);
                  goToNextStage();
                }
              }}
            >Continue →</button>
          </div>
        </div>
      );
    }

    // Substep 3: Collect contact info for selected professionals
    if (professionalSubStep === 3) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Please provide your professionals' contact information</h2>
            <p>We'll reach out to coordinate on your behalf.</p>
          </div>

          <div className="form-card professional-contacts-form">
            {selectedProfessionals.map((prof, index) => (
              <div key={prof} className="professional-contact-section">
                <h4><Icon name={PLANNING_QUESTIONS.professionalNetwork.options.find(o => o.value === prof)?.icon || 'user'} size={20} /> {professionalLabels[prof]}</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label>First Name</label>
                    <input
                      type="text"
                      className="fun-input"
                      placeholder="First name"
                      value={professionalContacts[prof]?.firstName || ''}
                      onChange={(e) => setProfessionalContacts(prev => ({
                        ...prev,
                        [prof]: { ...prev[prof], firstName: e.target.value }
                      }))}
                    />
                  </div>
                  <div className="form-group">
                    <label>Last Name</label>
                    <input
                      type="text"
                      className="fun-input"
                      placeholder="Last name"
                      value={professionalContacts[prof]?.lastName || ''}
                      onChange={(e) => setProfessionalContacts(prev => ({
                        ...prev,
                        [prof]: { ...prev[prof], lastName: e.target.value }
                      }))}
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      className="fun-input"
                      placeholder="(555) 123-4567"
                      value={professionalContacts[prof]?.phone || ''}
                      onChange={(e) => setProfessionalContacts(prev => ({
                        ...prev,
                        [prof]: { ...prev[prof], phone: e.target.value }
                      }))}
                    />
                  </div>
                  <div className="form-group">
                    <label>Email</label>
                    <input
                      type="email"
                      className="fun-input"
                      placeholder="email@example.com"
                      value={professionalContacts[prof]?.email || ''}
                      onChange={(e) => setProfessionalContacts(prev => ({
                        ...prev,
                        [prof]: { ...prev[prof], email: e.target.value }
                      }))}
                    />
                  </div>
                </div>
                {index < selectedProfessionals.length - 1 && <hr className="section-divider" />}
              </div>
            ))}
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setProfessionalSubStep(2)}>← Back</button>
            <button className="btn-continue" onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue →</button>
          </div>
        </div>
      );
    }

    // Substep 4: Ask if they want introductions to professionals (when none selected)
    if (professionalSubStep === 4) {
      return (
        <div className="stage-content planning-stage">
          <div className="stage-header">
            <h2>Would you like an introduction to a trusted professional?</h2>
            <p>We partner with qualified professionals who can help with your financial planning.</p>
          </div>

          <div className="form-card planning-section">
            <div className="single-select-options" style={{ marginBottom: '24px' }}>
              <button
                className={`single-select-option ${wantIntroductions === true ? 'selected' : ''}`}
                onClick={() => setWantIntroductions(true)}
              >
                <span className="option-icon"><Icon name="check" size={32} /></span>
                <span className="option-label">Yes, please connect me</span>
              </button>
              <button
                className={`single-select-option ${wantIntroductions === false ? 'selected' : ''}`}
                onClick={() => setWantIntroductions(false)}
              >
                <span className="option-icon"><Icon name="x" size={32} /></span>
                <span className="option-label">No thanks, not at this time</span>
              </button>
            </div>

            {wantIntroductions === true && (
              <div className="intro-selection">
                <h4>Select who you'd like to connect with:</h4>
                <div className="multi-select-grid compact">
                  {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
                    <button
                      key={option.value}
                      className={`multi-select-option ${introductionRequests.includes(option.value) ? 'selected' : ''}`}
                      onClick={() => {
                        setIntroductionRequests(prev =>
                          prev.includes(option.value)
                            ? prev.filter(v => v !== option.value)
                            : [...prev, option.value]
                        );
                      }}
                    >
                      <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                      <span className="option-label">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setProfessionalSubStep(1)}>← Back</button>
            <button
              className="btn-continue"
              disabled={wantIntroductions === null}
              onClick={() => { setPlanningStep(1); goToNextStage(); }}
            >Continue →</button>
          </div>
        </div>
      );
    }

    // Fallback
    return (
      <div className="stage-content planning-stage">
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(5)}>← Back</button>
          <button className="btn-continue" onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue →</button>
        </div>
      </div>
    );
  };

  // Generate available time slots
  const generateTimeSlots = () => {
    const slots = [];
    const today = new Date();
    for (let d = 1; d <= 5; d++) {
      const date = new Date(today);
      date.setDate(today.getDate() + d);
      if (date.getDay() === 0 || date.getDay() === 6) continue; // Skip weekends

      ['9:00 AM', '10:30 AM', '1:00 PM', '2:30 PM', '4:00 PM'].forEach(time => {
        slots.push({
          id: `${date.toISOString().split('T')[0]}-${time}`,
          date: date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
          time: time,
        });
      });
    }
    return slots.slice(0, 12); // Return first 12 slots
  };

  // Render schedule stage - split into 4 steps
  const renderScheduleStage = () => {
    const timeSlots = generateTimeSlots();

    // Step 1: Calendar selection
    if (scheduleStep === 1) {
      const bookingSlug = calendarAssignment?.booking_link_slug;
      const calendlyUrl = calendarAssignment?.calendly_url;

      // Booking link helpers
      const getWeekDates = () => {
        const dates = [];
        const start = new Date(bookingWeekStart);
        start.setHours(0, 0, 0, 0);
        for (let i = 0; i < 7; i++) {
          const d = new Date(start);
          d.setDate(start.getDate() + i);
          dates.push(d);
        }
        return dates;
      };

      const isPastDate = (d) => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return d < today;
      };

      const isTodayDate = (d) => d.toDateString() === new Date().toDateString();

      const formatDayName = (d) => d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
      const formatDayNumber = (d) => d.getDate();
      const formatMonth = (d) => d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
      const formatSlotTime = (timeStr) => {
        const dt = new Date(timeStr);
        return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
      };

      const prevWeek = () => {
        const newStart = new Date(bookingWeekStart);
        newStart.setDate(bookingWeekStart.getDate() - 7);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (newStart >= today) setBookingWeekStart(newStart);
      };

      const nextWeek = () => {
        const newStart = new Date(bookingWeekStart);
        newStart.setDate(bookingWeekStart.getDate() + 7);
        setBookingWeekStart(newStart);
      };

      const fetchBookingSlots = async (date) => {
        setBookingLoading(true);
        setBookingError(null);
        try {
          const dateStr = date.toISOString().split('T')[0];
          const response = await fetch(
            `${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/slots?date=${dateStr}`
          );
          if (response.ok) {
            const data = await response.json();
            const slots = (data.available_slots || []).map(slot => ({
              ...slot,
              start_time: slot.start,
              display: formatSlotTime(slot.start)
            }));
            setBookingSlots(slots);
            if (slots.length > 0) setBookingSelectedTime(slots[0].start_time);
            else setBookingSelectedTime('');
          }
        } catch (err) {
          console.error('Error fetching booking slots:', err);
          setBookingError('Failed to load available times');
        } finally {
          setBookingLoading(false);
        }
      };

      const handleDateSelect = (date) => {
        setBookingSelectedDate(date);
        setBookingSelectedTime('');
        setBookingSlots([]);
        fetchBookingSlots(date);
      };

      const handleConfirmBooking = async () => {
        if (!bookingSelectedTime) return;
        setBookingLoading(true);
        setBookingError(null);
        try {
          const response = await fetch(`${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              start_time: bookingSelectedTime,
              duration_minutes: 30,
              attendee_name: `${profileData?.firstName || ''} ${profileData?.lastName || ''}`.trim() || 'Applicant',
              attendee_email: profileData?.email || '',
              attendee_phone: profileData?.phone || '',
              notes: 'Booked from Purchase Application',
              meeting_mode: 'video'
            })
          });

          if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to book appointment');
          }

          setBookingConfirmed(true);
          showMicroWinAnimation('Consultation Scheduled!');
          setScheduleStep(2);
        } catch (err) {
          console.error('Error confirming booking:', err);
          setBookingError(err.message || 'Failed to book appointment');
        } finally {
          setBookingLoading(false);
        }
      };

      const weekDates = bookingSlug ? getWeekDates() : [];

      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>Schedule Your Consultation</h2>
            <p>Let's find a time that works for you to discuss your mortgage options.</p>
          </div>

          <div className="calendar-section">
            {bookingSlug ? (
              // Native booking link slot picker
              <div className="booking-slot-picker">
                <h4>Pick a Date</h4>
                <div className="booking-week-picker">
                  <button className="week-nav-btn" onClick={prevWeek} disabled={isPastDate(weekDates[0])}>
                    &#8249;
                  </button>
                  <div className="booking-week-dates">
                    {weekDates.map((date, idx) => {
                      const disabled = isPastDate(date);
                      const selected = bookingSelectedDate && date.toDateString() === bookingSelectedDate.toDateString();
                      return (
                        <button
                          key={idx}
                          className={`booking-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isTodayDate(date) ? 'today' : ''}`}
                          onClick={() => !disabled && handleDateSelect(date)}
                          disabled={disabled}
                        >
                          <span className="booking-day-name">{formatDayName(date)}</span>
                          <span className="booking-day-number">{formatDayNumber(date)}</span>
                          <span className="booking-month">{formatMonth(date)}</span>
                        </button>
                      );
                    })}
                  </div>
                  <button className="week-nav-btn" onClick={nextWeek}>
                    &#8250;
                  </button>
                </div>

                {bookingSelectedDate && (
                  <div className="booking-time-section">
                    <h4>Pick a Time</h4>
                    {bookingLoading ? (
                      <div className="booking-loading">Loading available times...</div>
                    ) : bookingError ? (
                      <div className="booking-error">{bookingError}</div>
                    ) : bookingSlots.length === 0 ? (
                      <div className="booking-no-slots">No times available for this date. Try another day.</div>
                    ) : (
                      <>
                        <div className="booking-time-grid">
                          {bookingSlots.map((slot, idx) => (
                            <button
                              key={idx}
                              className={`booking-time-btn ${bookingSelectedTime === slot.start_time ? 'selected' : ''}`}
                              onClick={() => setBookingSelectedTime(slot.start_time)}
                            >
                              {slot.display}
                            </button>
                          ))}
                        </div>

                        <button
                          className="btn-schedule"
                          disabled={!bookingSelectedTime || bookingLoading}
                          onClick={handleConfirmBooking}
                        >
                          {bookingLoading ? 'Booking...' : 'Confirm Appointment'}
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ) : calendlyUrl ? (
              // Show Calendly embed when configured
              <div className="calendly-embed-container">
                <iframe
                  src={`${calendlyUrl}?hide_gdpr_banner=1&hide_event_type_details=1`}
                  width="100%"
                  height="630"
                  frameBorder="0"
                  title="Schedule Consultation"
                  style={{ minWidth: '320px', borderRadius: '8px' }}
                ></iframe>
                <div className="calendly-skip-option">
                  <p>After scheduling, click Continue to proceed with your application.</p>
                  <button
                    className="btn-schedule"
                    onClick={() => {
                      showMicroWinAnimation('Moving to next step!');
                      setScheduleStep(2);
                    }}
                  >
                    Continue →
                  </button>
                </div>
              </div>
            ) : (
              // Fallback to mock time slots when nothing configured
              <div className="calendar-placeholder">
                <span className="cal-icon"><Icon name="calendar" size={48} /></span>
                <h4>Pick a Time That Works For You</h4>
                <p>We want to coordinate a time to review the application with you. Choose a time that is most convenient for you.</p>

                <div className="time-slots">
                  {timeSlots.map(slot => (
                    <div
                      key={slot.id}
                      className={`time-slot ${selectedTimeSlot === slot.id ? 'selected' : ''}`}
                      onClick={() => setSelectedTimeSlot(slot.id)}
                    >
                      <div className="time-slot-time">{slot.time}</div>
                      <div className="time-slot-date">{slot.date}</div>
                    </div>
                  ))}
                </div>

                <button
                  className="btn-schedule"
                  disabled={!selectedTimeSlot}
                  onClick={() => {
                    showMicroWinAnimation('Consultation Scheduled!');
                    setScheduleStep(2);
                  }}
                >
                  {selectedTimeSlot ? 'Confirm Appointment' : 'Select a Time Slot'}
                </button>
              </div>
            )}
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          </div>
        </div>
      );
    }

    // Step 2: E-Consent Page
    if (scheduleStep === 2) {
      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>E-Consent Documentation</h2>
            <p>Please review and consent to receive documents electronically.</p>
          </div>

          <div className="econsent-section econsent-full-page">
            <div className="econsent-content">
              <p className="econsent-intro">
                To use electronic signatures and receive documents electronically in connection with your use of this
                platform, you must read and consent to the terms outlined in this document, which require your ability to
                access and retain electronic documents.
              </p>

              <div className="econsent-scrollbox">
                <p>
                  This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a
                  desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan
                  documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing
                  notices, and any other loan documents that we provide to you in electronic form.
                </p>

                <p>
                  If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in
                  other portals, and/or through other methods we may use for delivery of electronic Documents. With Your
                  eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper.
                  Anytime you are signing using a platform contracted with nCino Mortgage, you will be prompted to provide
                  eConsent again.
                </p>

                <p>
                  Before We can engage in this transaction electronically, it is important that You understand Your rights and
                  responsibilities. Please read the following and affirm Your consent to conduct business with Us electronically.
                  For purposes of this eConsent Agreement, 'You' and 'Your' mean the borrower(s) under the applicable loan to
                  which such Documents apply, and 'We', 'Our' and 'Us' mean the applicable mortgage broker(s), loan
                  processor(s), or mortgage banker(s) with whom You are transacting business for such loan(s).
                </p>

                <h4>Your Consent</h4>
                <p>
                  Your consent to participate in this transaction electronically will apply to all Loan Documents for the
                  applicable loans for which You are applying. If You provide Your consent by clicking the 'I agree'
                  button at the bottom of the page, We will conduct this transaction electronically, instead of providing
                  You with the Loan Documents in paper form.
                </p>
                <p>
                  If a document related to Your loan is not available in electronic form, a paper copy will be provided to
                  You free of charge.
                </p>
                <p>
                  Conducting this transaction electronically is an option. If You choose not to receive Documents
                  electronically, paper Documents will be mailed to You. Additionally: You will not be required to pay a
                  fee for receiving paper copies of the Documents.
                </p>

                <h4>Withdrawal of Consent</h4>
                <p>
                  You have the right to withdraw Your consent at any time. By declining or revoking Your consent to
                  receive Documents electronically, We will provide You with the Documents in paper form.
                </p>
                <p>
                  If You originally consent to receive Documents electronically, but later decide to withdraw Your
                  consent, You can do so by clicking on the 'I do not agree' button, or by contacting Us by phone.
                </p>
                <p>
                  If You originally consent to receive Documents electronically, but later withdraw Your consent, You
                  will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.
                </p>

                <h4>Obtaining Paper Copies</h4>
                <p>
                  After Your consent is given, You may request from Us paper copies of Your Loan Documents by contacting Us.
                  If You request paper copies of the Loan Documents, You will not be required to pay a fee for receiving
                  paper copies of the Loan Documents.
                </p>

                <h4>System Requirements</h4>
                <p>
                  In order to receive Documents electronically, You must have a computer with Internet access and an
                  Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe
                  Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in
                  order to keep copies of Your Documents electronically for Your records.
                </p>
                <p>
                  If the software or hardware requirements change in the future, and You are unable to continue receiving
                  Documents electronically, paper copies of such Loan Documents will be mailed to You once You
                  notify Us that You are no longer able to access the Documents electronically because of the changed
                  requirements. We will use commercially reasonable efforts to notify You before such requirements
                  change. If You choose to withdraw Your consent upon notification of the change, You will be able to
                  do so without penalty.
                </p>

                <h4>How Can We Reach You</h4>
                <p>
                  You must promptly notify Us if there is a change in Your email address or in other information needed
                  to contact You electronically.
                </p>
                <p>
                  We will not assume liability for non-receipt of notification of the availability of Documents
                  electronically in the event Your email address on file is invalid; Your email or Internet service provider
                  filters the notification as 'spam' or 'junk mail'; there is a malfunction in Your computer, browser, Internet
                  service and/or software; or for other reasons beyond Our control.
                </p>
              </div>

              <div className="econsent-actions">
                <button
                  className={`econsent-btn agree ${eConsentAgreed ? 'selected' : ''}`}
                  onClick={() => setEConsentAgreed(true)}
                >
                  <Icon name="check" size={18} />
                  I Agree
                </button>
                <button
                  className="econsent-btn disagree"
                  onClick={() => {
                    setEConsentAgreed(false);
                    toast.success('You have chosen not to consent to electronic documents. Paper documents will be mailed to you. You can still proceed with your application.');
                  }}
                >
                  I Do Not Agree
                </button>
              </div>
            </div>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setScheduleStep(1)}>← Back</button>
            <button
              className="btn-continue"
              disabled={!eConsentAgreed}
              onClick={() => setScheduleStep(3)}
            >
              {eConsentAgreed ? 'Continue →' : 'Please Accept E-Consent to Continue'}
            </button>
          </div>
        </div>
      );
    }

    // Step 3: Credit Authorization Page
    if (scheduleStep === 3) {
      return (
        <div className="stage-content scheduling-page">
          <div className="scheduling-header">
            <h2>Credit Authorization</h2>
            <p>Please authorize us to check your credit to provide accurate mortgage options.</p>
          </div>

          <div className="econsent-section credit-auth-section econsent-full-page">
            <div className="econsent-content">
              <p className="econsent-intro">
                Your credit information will help us understand more about your personal and financial background and
                ensure we give you the most accurate mortgage options. To help us, we need the following authorization:
              </p>

              <div className="credit-auth-box">
                <p>
                  I authorize my Lender to perform a credit check, via either a soft or hard pull of my credit; I understand this
                  may affect my credit score. I acknowledge that any owner of a completed loan, its servicers, successors and
                  assigns, may verify or re-verify any information contained in this form or obtain any information or data
                  relating to a completed loan, for any legitimate purpose, through any source, including a source named in this
                  form or a consumer reporting agency.
                </p>
              </div>

              <div className="econsent-actions">
                <button
                  className={`econsent-btn agree ${creditAuthAgreed ? 'selected' : ''}`}
                  onClick={() => setCreditAuthAgreed(true)}
                >
                  <Icon name="check" size={18} />
                  I Authorize
                </button>
                <button
                  className="econsent-btn disagree"
                  onClick={() => {
                    setCreditAuthAgreed(false);
                    toast.error('Credit authorization is required to process your mortgage application. Without it, we cannot verify your creditworthiness.');
                  }}
                >
                  I Do Not Authorize
                </button>
              </div>
            </div>
          </div>

          {submitError && (
            <div className="error-message" style={{
              color: '#dc3545',
              backgroundColor: '#f8d7da',
              padding: '12px 16px',
              borderRadius: '8px',
              marginBottom: '16px',
              textAlign: 'center'
            }}>
              {submitError}
            </div>
          )}

          <div className="submit-section">
            <button
              className="btn-submit"
              disabled={!creditAuthAgreed || isSubmitting}
              onClick={handleSubmitApplication}
            >
              {isSubmitting
                ? 'Submitting...'
                : creditAuthAgreed
                  ? 'Submit Application'
                  : 'Please Authorize Credit Check to Submit'}
            </button>
          </div>

          <div className="stage-navigation">
            <button className="btn-back" onClick={() => setScheduleStep(2)} disabled={isSubmitting}>← Back</button>
          </div>
        </div>
      );
    }

    // Step 4: Confirmation Page (Video and next steps)
    return (
      <div className="stage-content scheduling-page confirmation-page">
        <div className="scheduling-header">
          <div className="success-icon">
            <Icon name="check" size={48} />
          </div>
          <h2>Application Submitted!</h2>
          <p>Congratulations! Your mortgage application has been successfully submitted.</p>
        </div>

        <div className="video-section">
          <div className="video-container">
            <div className="video-placeholder">
              <span className="play-icon"><Icon name="play" size={48} /></span>
              <p>What to Expect: Your Home Buying Journey</p>
            </div>
          </div>

          <div className="next-steps-list">
            <h3><Icon name="clipboard" size={18} /> What Happens Next</h3>
            <ol>
              <li><strong>Consultation Call</strong> - We'll review your application and answer any questions</li>
              <li><strong>Document Collection</strong> - Upload your documents through our secure portal</li>
              <li><strong>Pre-Approval Letter</strong> - Receive your pre-approval to make offers with confidence</li>
              <li><strong>Find Your Dream Home</strong> - Shop with confidence knowing your financing is ready</li>
            </ol>
          </div>
        </div>

        <div className="confirmation-message">
          <p><strong>Check your email</strong> for confirmation and document upload instructions.</p>
        </div>
      </div>
    );
  };

  // Render current stage
  const renderStage = () => {
    switch (currentStage) {
      case 'account': return renderAccountStage();
      case 'declarations': return renderDeclarationsStage();
      case 'profile': return renderProfileStage();
      case 'income': return renderIncomeStage();
      case 'assets': return renderAssetsStage();
      case 'property': return renderPropertyStage();
      case 'review': return renderReviewStage();
      case 'planning': return renderPlanningStage();
      case 'schedule': return renderScheduleStage();
      default: return renderAccountStage();
    }
  };

  return (
    <div className="adaptive-urla">
      {isDemoMode && (
        <div className="demo-banner">
          <span className="demo-badge">DEMO</span>
          Home Purchase Application
        </div>
      )}

      {/* Hide progress header during account creation */}
      {currentStage !== 'account' && (
        <div className="progress-header">
          <div className="progress-chapters">
            {visibleStages.map((stage, index) => {
              const currentIndex = visibleStages.findIndex(s => s.id === currentStage);
              const isComplete = index < currentIndex;
              const isCurrent = index === currentIndex;
              return (
                <div
                  key={stage.id}
                  className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} clickable`}
                  onClick={() => setCurrentStage(stage.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <span className="chapter-icon">{isComplete ? <Icon name="check" size={20} /> : <Icon name={stage.icon} size={20} />}</span>
                  <span className="chapter-label">{stage.label}</span>
                </div>
              );
            })}
          </div>
          <div className="progress-bar-container" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div className="progress-bar" style={{ flex: 1 }}>
              <div className="progress-fill" style={{ width: `${getProgress()}%` }}></div>
            </div>
            <span className="progress-text">{getProgress()}% Complete</span>

            {/* Save Progress Button */}
            <button
              onClick={() => setShowSaveModal(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                background: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: 500,
                color: '#374151',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.target.style.background = '#f3f4f6';
                e.target.style.borderColor = '#d1d5db';
              }}
              onMouseLeave={(e) => {
                e.target.style.background = 'white';
                e.target.style.borderColor = '#e5e7eb';
              }}
            >
              <Icon name="save" size={16} />
              Save
            </button>
          </div>
        </div>
      )}

      {/* Save Progress Modal */}
      {showSaveModal && (
        <div className="modal-overlay" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div className="save-modal" style={{
            background: 'white',
            borderRadius: '16px',
            padding: '32px',
            maxWidth: '420px',
            width: '90%',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)'
          }}>
            <h3 style={{ marginTop: 0, marginBottom: '8px' }}>Save Your Progress</h3>
            <p style={{ color: '#6b7280', marginBottom: '20px', fontSize: '14px' }}>
              Your application is automatically saved to this browser. Enter your email to save to the cloud and access from any device.
            </p>

            {lastSavedAt && (
              <p style={{
                background: '#f0fdf4',
                padding: '10px 14px',
                borderRadius: '8px',
                color: '#166534',
                fontSize: '13px',
                marginBottom: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <Icon name="check" size={16} />
                Auto-saved to browser {lastSavedAt.toLocaleTimeString()}
              </p>
            )}

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, fontSize: '14px' }}>
                Email Address (optional)
              </label>
              <input
                type="email"
                value={saveEmail || userAccount.email}
                onChange={(e) => setSaveEmail(e.target.value)}
                placeholder="you@example.com"
                className="fun-input"
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => {
                  setShowSaveModal(false);
                  if (saveEmail) {
                    setUserAccount(prev => ({ ...prev, email: saveEmail }));
                  }
                }}
                style={{
                  flex: 1,
                  padding: '12px',
                  background: '#0d9488',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 500,
                  cursor: 'pointer'
                }}
              >
                {saveEmail ? 'Save & Send Magic Link' : 'Got it!'}
              </button>
              <button
                onClick={() => setShowSaveModal(false)}
                style={{
                  padding: '12px 20px',
                  background: 'transparent',
                  color: '#6b7280',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontWeight: 500,
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {showMicroWin && (
        <div className="micro-win-toast">
          <span className="micro-win-icon"><Icon name="check" size={24} /></span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      <div className="urla-main-layout">
        <main className="urla-content">
          {renderStage()}
        </main>

        {/* Documents Sidebar - Shows container, documents populate as questions are answered */}
        {currentStage !== 'account' && (
        <aside className="documents-sidebar">
          <div className="sidebar-header">
            <Icon name="document" size={20} />
            <h3>Documents Needed</h3>
          </div>
          <p className="sidebar-subtitle">Gather these documents to speed up your application</p>

          <div className="documents-list">
            {(() => {
              const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
              // Get dynamic document list with personalized labels (borrower names, employer names, years)
              const requiredDocs = getRequiredDocuments(
                declarations,
                assetData,
                profileData,
                incomeData,
                coBorrowerData,
                coBorrowerIncomeData
              );

              // Map category to the stage that unlocks it
              const categoryUnlockStage = {
                identity: 'declarations',
                income: 'income',
                assets: 'assets',
                property: 'property'
              };

              const categoryLabels = {
                identity: 'Identity Verification',
                income: 'Income Documents',
                assets: 'Asset Documents',
                property: 'Property Documents'
              };

              // Filter categories to only show those that have been unlocked AND have documents
              const visibleCategories = ['identity', 'income', 'assets', 'property'].filter(category => {
                const unlockStage = categoryUnlockStage[category];
                const unlockIndex = enabledStages.findIndex(s => s.id === unlockStage);
                const categoryDocs = requiredDocs.filter(d => d.category === category);
                // Show category if user has reached or passed its unlock stage AND has documents
                return currentIndex >= unlockIndex && categoryDocs.length > 0;
              });

              return visibleCategories.map(category => {
                const categoryDocs = requiredDocs.filter(d => d.category === category);
                const isCurrent = categoryDocs.some(d => d.stage === currentStage);

                return (
                  <div key={category} className={`doc-category ${isCurrent ? 'current' : ''}`}>
                    <h4 className="doc-category-title">{categoryLabels[category]}</h4>
                    <ul className="doc-items">
                      {categoryDocs.map(doc => (
                        <li key={doc.id} className="doc-item">
                          <span className="doc-checkbox">
                            <Icon name="document" size={14} />
                          </span>
                          <div className="doc-info">
                            <span className="doc-name">{doc.name}</span>
                            <span className="doc-desc">{doc.description}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              });
            })()}
          </div>

          <div className="sidebar-tip">
            <Icon name="info" size={16} />
            <span>You can upload documents after submitting your application</span>
          </div>
        </aside>
        )}
      </div>

      {/* Submission Success Lightbox */}
      {showSubmissionSuccess && (
        <div className="submission-success-overlay">
          <div className="submission-success-lightbox">
            <div className="success-checkmark">
              <svg viewBox="0 0 52 52" className="checkmark-svg">
                <circle className="checkmark-circle" cx="26" cy="26" r="25" fill="none"/>
                <path className="checkmark-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
              </svg>
            </div>
            <h2>Application Submitted!</h2>
            <p>Your mortgage application has been successfully submitted.</p>
            <p className="redirect-message">You will be redirected to your client portal...</p>
          </div>
        </div>
      )}
    </div>
  );
}
