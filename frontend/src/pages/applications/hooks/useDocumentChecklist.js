/**
 * useDocumentChecklist - Dynamic document requirements based on application data
 * Generates personalized document list based on borrower circumstances
 */

import { useMemo } from 'react';
import { useApplication } from '../contexts/ApplicationContext';

// Document categories for organization
export const DocumentCategories = {
  IDENTITY: 'identity',
  INCOME: 'income',
  ASSETS: 'assets',
  PROPERTY: 'property',
  CREDIT: 'credit',
};

/**
 * Generate required documents based on application data
 * @param {Object} formData - All form data from the application
 * @returns {Array} List of required documents with metadata
 */
export const getRequiredDocuments = (formData = {}) => {
  const docs = [];

  // Extract relevant data
  const {
    // Borrower info
    borrower_count,
    citizenship_status,
    citizenship, // Alternative field name from form

    // Primary borrower names
    first_name: borrowerFirstName = 'Primary Borrower',

    // Co-borrower info
    coborrower_first_name: coBorrowerFirstName = 'Co-Borrower',

    // Employment
    employment_type,
    self_employed,
    business_name,
    business_type,
    write_off_expenses,
    employer_name: primaryEmployer,
    coborrower_employer_name: coBorrowerEmployer,

    // Veteran status
    veteran_status,
    va_disability,

    // Marital/divorce
    marital_status,
    child_support_alimony,

    // Credit history
    credit_issues,
    bankruptcy_type,
    bankruptcy_discharge_ch7,
    chapter_13_status,
    recent_credit_applications,
    credit_application_approved,
    credit_application_type,

    // Tax status
    irs_balance_owed,
    prior_year_taxes_filed,

    // Property ownership
    first_time_buyer,
    previous_home_status,
    previous_home_mortgage,

    // Assets
    checking_balance,
    savings_balance,
    investment_balance,
    retirement_balance,
    gift_funds,

    // Refinance specific
    refinance_purpose,
    current_mortgage_balance,
    second_mortgage_balance,
  } = formData;

  // Calculate date-based document requirements
  const today = new Date();
  const currentYear = today.getFullYear();
  const priorYear = currentYear - 1;
  const twoYearsAgo = currentYear - 2;
  const jan28 = new Date(currentYear, 0, 28);
  const isBeforeJan28 = today < jan28;

  // Helper to determine self-employed status
  const isSelfEmployed = employment_type === 'self_employed' ||
                         self_employed === 'yes' ||
                         self_employed === 'side_business';

  // Helper to check for co-borrowers
  const hasCoBorrower = ['2', '3', '4+'].includes(borrower_count);

  // Helper to check asset values
  const hasCheckingOrSavings = (parseFloat(checking_balance) || 0) > 0 ||
                               (parseFloat(savings_balance) || 0) > 0;
  const hasInvestmentOrRetirement = (parseFloat(investment_balance) || 0) > 0 ||
                                    (parseFloat(retirement_balance) || 0) > 0;
  const hasGiftFunds = gift_funds === 'yes';
  const maximizesDeductions = write_off_expenses === 'yes';

  // === IDENTITY DOCUMENTS ===
  // Use citizenship_status or citizenship field (depends on form)
  const citizenshipValue = citizenship_status || citizenship;

  if (citizenshipValue) {
    docs.push({
      id: 'id',
      name: `${borrowerFirstName}'s Government ID`,
      description: "Driver's license or passport",
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: true,
    });
  }

  // Citizenship-based documents
  if (citizenshipValue === 'permanent_resident') {
    docs.push({
      id: 'green_card',
      name: `${borrowerFirstName}'s Green Card`,
      description: 'Unexpired Permanent Resident Card (front and back)',
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: true,
    });
  }

  if (citizenshipValue === 'non_permanent_resident' || citizenshipValue === 'non_resident') {
    docs.push({
      id: 'visa_docs',
      name: `${borrowerFirstName}'s Visa Documents`,
      description: 'Current visa, work authorization (EAD card if applicable), and I-94',
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: true,
    });
  }

  // === INCOME DOCUMENTS ===
  const businessNameLabel = business_name?.trim() || 'your business';
  const employerLabel = primaryEmployer?.trim() || 'your employer';

  if (isSelfEmployed) {
    if (maximizesDeductions) {
      // Heavy deductions - use bank statement program
      docs.push({
        id: 'business_bank_statements',
        name: `${borrowerFirstName}'s Business Bank Statements`,
        description: `12 consecutive months of bank statements for ${businessNameLabel}`,
        category: DocumentCategories.INCOME,
        stage: 'income',
        required: true,
      });
    } else {
      // Standard self-employed documentation
      if (isBeforeJan28) {
        // Before Jan 28 - prior year taxes can't be filed yet
        docs.push({
          id: 'tax_returns',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'business_tax_returns',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessNameLabel} ${twoYearsAgo} business tax return`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'profit_loss',
          name: `${priorYear} Profit & Loss Statement`,
          description: `Year-to-date ${priorYear} P&L for ${businessNameLabel} (signed by ${borrowerFirstName})`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
      } else if (prior_year_taxes_filed === 'yes') {
        // After Jan 28 and taxes filed
        docs.push({
          id: 'tax_returns_recent',
          name: `${borrowerFirstName}'s ${priorYear} Personal Tax Return`,
          description: `Complete ${priorYear} personal tax return (all pages & schedules)`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'tax_returns_prior',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'business_tax_returns_recent',
          name: `${priorYear} Business Tax Return`,
          description: `${businessNameLabel} ${priorYear} business tax return`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'business_tax_returns_prior',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessNameLabel} ${twoYearsAgo} business tax return`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
      } else {
        // After Jan 28 but taxes not filed
        docs.push({
          id: 'tax_returns',
          name: `${borrowerFirstName}'s ${twoYearsAgo} Personal Tax Return`,
          description: `Complete ${twoYearsAgo} personal tax return (all pages & schedules)`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'business_tax_returns',
          name: `${twoYearsAgo} Business Tax Return`,
          description: `${businessNameLabel} ${twoYearsAgo} business tax return`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
        docs.push({
          id: 'profit_loss',
          name: `${priorYear} Profit & Loss Statement`,
          description: `Year-to-date ${priorYear} P&L for ${businessNameLabel} (signed by ${borrowerFirstName})`,
          category: DocumentCategories.INCOME,
          stage: 'income',
          required: true,
        });
      }
    }

    // Articles of Incorporation for S-Corp or C-Corp
    if (business_type === 's_corp' || business_type === 'c_corp') {
      docs.push({
        id: 'articles_incorporation',
        name: `${businessNameLabel} Articles of Incorporation`,
        description: 'Corporate formation documents showing ownership',
        category: DocumentCategories.INCOME,
        stage: 'income',
        required: true,
      });
    }
  } else {
    // W-2 employee
    docs.push({
      id: 'paystubs',
      name: `${borrowerFirstName}'s Pay Stubs from ${employerLabel}`,
      description: `2 consecutive recent pay stubs from ${employerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });
    docs.push({
      id: 'w2_recent',
      name: `${borrowerFirstName}'s ${priorYear} W-2 from ${employerLabel}`,
      description: `${priorYear} W-2 form from ${employerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });
    docs.push({
      id: 'w2_prior',
      name: `${borrowerFirstName}'s ${twoYearsAgo} W-2 from ${employerLabel}`,
      description: `${twoYearsAgo} W-2 form from ${employerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });
  }

  // === DIVORCE / CHILD SUPPORT DOCUMENTS ===
  // Divorce decree is always required for divorced applicants
  if (marital_status === 'divorced' || marital_status === 'separated') {
    docs.push({
      id: 'divorce_decree',
      name: `${borrowerFirstName}'s Divorce Decree`,
      description: 'Final divorce decree with property/support terms',
      category: DocumentCategories.INCOME,
      stage: 'about_you',
      required: true,
    });
    docs.push({
      id: 'property_settlement',
      name: 'Property Settlement Agreement',
      description: 'Marital settlement agreement (if separate from decree)',
      category: DocumentCategories.INCOME,
      stage: 'about_you',
      required: false,
    });
  }

  // === VETERAN DOCUMENTS ===
  // Match form values: 'veteran', 'active_duty', 'spouse_veteran', 'yes', 'active', 'spouse'
  const isVeteran = ['veteran', 'active_duty', 'spouse_veteran', 'yes', 'active', 'spouse'].includes(veteran_status);
  if (isVeteran) {
    docs.push({
      id: 'va_coe',
      name: `${borrowerFirstName}'s VA Certificate of Eligibility`,
      description: 'VA COE - can be obtained from eBenefits portal or requested through lender',
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: true,
    });
  }

  if (va_disability === 'pending') {
    docs.push({
      id: 'va_pending_claim',
      name: 'VA Pending Disability Claim',
      description: 'Documentation of pending VA disability claim',
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: false,
    });
  }

  // === IRS DOCUMENTS ===
  if (irs_balance_owed === 'payment_plan') {
    docs.push({
      id: 'irs_payment_arrangement',
      name: `${borrowerFirstName}'s IRS Payment Arrangement`,
      description: 'IRS installment agreement letter showing payment terms',
      category: DocumentCategories.INCOME,
      stage: 'background',
      required: true,
    });
  } else if (irs_balance_owed === 'yes') {
    docs.push({
      id: 'irs_payoff',
      name: `${borrowerFirstName}'s IRS Payoff Statement`,
      description: 'Current IRS balance and payoff amount',
      category: DocumentCategories.INCOME,
      stage: 'background',
      required: true,
    });
  }

  // === PREVIOUS HOME / RENTAL PROPERTY DOCUMENTS ===
  if (previous_home_mortgage === 'yes' || current_mortgage_balance) {
    docs.push({
      id: 'existing_mortgage_statement',
      name: 'Current Mortgage Statement',
      description: 'Most recent mortgage statement for existing property',
      category: DocumentCategories.ASSETS,
      stage: 'property',
      required: true,
    });
  }

  if (previous_home_status === 'renting_out') {
    docs.push({
      id: 'rental_tax_returns',
      name: `${borrowerFirstName}'s Tax Return with Schedule E`,
      description: `${priorYear} tax return showing rental income (Schedule E)`,
      category: DocumentCategories.INCOME,
      stage: 'real_estate_owned',
      required: true,
    });
    docs.push({
      id: 'lease_agreement',
      name: 'Current Lease Agreement',
      description: 'Signed lease agreement for rental property',
      category: DocumentCategories.ASSETS,
      stage: 'real_estate_owned',
      required: true,
    });
  }

  // === CREDIT APPLICATION DOCUMENTS ===
  if (recent_credit_applications === 'yes' && credit_application_approved === 'yes') {
    const creditLabels = {
      'auto_loan': 'Auto Loan Statement',
      'credit_card': 'Credit Card Statement',
      'personal_loan': 'Personal Loan Statement',
      'other': 'New Account Statement',
    };
    const label = creditLabels[credit_application_type] || 'New Account Statement';
    docs.push({
      id: 'new_credit_statement',
      name: `${borrowerFirstName}'s ${label}`,
      description: 'Statement showing account balance and payment for recently opened account',
      category: DocumentCategories.CREDIT,
      stage: 'background',
      required: true,
    });
  }

  // === BANKRUPTCY DOCUMENTS ===
  if (credit_issues === 'bankruptcy') {
    if (bankruptcy_type === 'chapter_7') {
      if (bankruptcy_discharge_ch7 !== '8_years_or_more') {
        docs.push({
          id: 'bankruptcy_docs',
          name: `${borrowerFirstName}'s Chapter 7 Bankruptcy Discharge`,
          description: 'Chapter 7 discharge papers showing case number and discharge date',
          category: DocumentCategories.CREDIT,
          stage: 'background',
          required: true,
        });
      }
    } else if (bankruptcy_type === 'chapter_13') {
      if (chapter_13_status === 'active_paying') {
        docs.push({
          id: 'ch13_payment_history',
          name: 'Chapter 13 Payment History',
          description: '12-month payment history from Chapter 13 trustee',
          category: DocumentCategories.CREDIT,
          stage: 'background',
          required: true,
        });
        docs.push({
          id: 'ch13_court_approval',
          name: 'Court Approval for New Mortgage',
          description: 'Court letter approving new mortgage while in Chapter 13',
          category: DocumentCategories.CREDIT,
          stage: 'background',
          required: true,
        });
      } else {
        docs.push({
          id: 'bankruptcy_discharge',
          name: `${borrowerFirstName}'s Chapter 13 Discharge`,
          description: 'Chapter 13 discharge documents',
          category: DocumentCategories.CREDIT,
          stage: 'background',
          required: true,
        });
      }
    } else if (bankruptcy_type === 'chapter_12') {
      docs.push({
        id: 'ch12_payment_history',
        name: 'Chapter 12 Payment History',
        description: '12-month payment history from trustee',
        category: DocumentCategories.CREDIT,
        stage: 'background',
        required: true,
      });
      docs.push({
        id: 'ch12_court_approval',
        name: 'Court Approval Letter',
        description: 'Court approval letter for new financing',
        category: DocumentCategories.CREDIT,
        stage: 'background',
        required: true,
      });
    }
  }

  // === ASSET DOCUMENTS ===
  if (hasCheckingOrSavings) {
    docs.push({
      id: 'bank_statements',
      name: `${borrowerFirstName}'s Bank Statements`,
      description: 'Last 2 complete months for all checking/savings accounts',
      category: DocumentCategories.ASSETS,
      stage: 'assets',
      required: true,
    });
  }

  if (hasInvestmentOrRetirement) {
    docs.push({
      id: 'investment_statements',
      name: `${borrowerFirstName}'s Investment/Retirement Statements`,
      description: 'Most recent quarterly statements for investment & retirement accounts',
      category: DocumentCategories.ASSETS,
      stage: 'assets',
      required: true,
    });
  }

  if (hasGiftFunds) {
    docs.push({
      id: 'gift_letter',
      name: 'Gift Letter',
      description: `Signed gift letter from donor to ${borrowerFirstName}`,
      category: DocumentCategories.ASSETS,
      stage: 'assets',
      required: true,
    });
  }

  // === SECOND MORTGAGE DOCUMENTS (Refinance) ===
  if (second_mortgage_balance && parseFloat(second_mortgage_balance) > 0) {
    docs.push({
      id: 'second_mortgage_statement',
      name: 'Second Mortgage/HELOC Statement',
      description: 'Most recent statement for second mortgage or HELOC',
      category: DocumentCategories.ASSETS,
      stage: 'current_mortgage',
      required: true,
    });
  }

  // === CO-BORROWER DOCUMENTS ===
  if (hasCoBorrower) {
    const coBorrowerEmployerLabel = coBorrowerEmployer?.trim() || `${coBorrowerFirstName}'s employer`;

    docs.push({
      id: 'coborrower_id',
      name: `${coBorrowerFirstName}'s Government ID`,
      description: `${coBorrowerFirstName}'s driver's license or passport`,
      category: DocumentCategories.IDENTITY,
      stage: 'about_you',
      required: true,
    });

    docs.push({
      id: 'coborrower_paystubs',
      name: `${coBorrowerFirstName}'s Pay Stubs from ${coBorrowerEmployerLabel}`,
      description: `2 consecutive recent pay stubs from ${coBorrowerEmployerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });
    docs.push({
      id: 'coborrower_w2_recent',
      name: `${coBorrowerFirstName}'s ${priorYear} W-2 from ${coBorrowerEmployerLabel}`,
      description: `${priorYear} W-2 form from ${coBorrowerEmployerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });
    docs.push({
      id: 'coborrower_w2_prior',
      name: `${coBorrowerFirstName}'s ${twoYearsAgo} W-2 from ${coBorrowerEmployerLabel}`,
      description: `${twoYearsAgo} W-2 form from ${coBorrowerEmployerLabel}`,
      category: DocumentCategories.INCOME,
      stage: 'income',
      required: true,
    });

    docs.push({
      id: 'coborrower_bank_statements',
      name: `${coBorrowerFirstName}'s Bank Statements`,
      description: `Last 2 complete months for ${coBorrowerFirstName}'s accounts (if separate from ${borrowerFirstName})`,
      category: DocumentCategories.ASSETS,
      stage: 'assets',
      required: false,
    });
  }

  return docs;
};

/**
 * Group documents by category
 * @param {Array} docs - List of documents
 * @returns {Object} Documents grouped by category
 */
export const groupDocumentsByCategory = (docs) => {
  return docs.reduce((acc, doc) => {
    const category = doc.category || 'other';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(doc);
    return acc;
  }, {});
};

/**
 * Get category label for display
 * @param {string} category - Category key
 * @returns {string} Human-readable category label
 */
export const getCategoryLabel = (category) => {
  const labels = {
    [DocumentCategories.IDENTITY]: 'Identity Documents',
    [DocumentCategories.INCOME]: 'Income Documents',
    [DocumentCategories.ASSETS]: 'Asset Documents',
    [DocumentCategories.PROPERTY]: 'Property Documents',
    [DocumentCategories.CREDIT]: 'Credit Documents',
    other: 'Other Documents',
  };
  return labels[category] || 'Documents';
};

/**
 * Hook to get required documents based on current application state
 * @returns {Object} Document checklist data and helpers
 */
export const useDocumentChecklist = () => {
  const { state } = useApplication();
  const { formData } = state;

  // Generate required documents based on form data
  const requiredDocuments = useMemo(
    () => getRequiredDocuments(formData),
    [formData]
  );

  // Group documents by category
  const documentsByCategory = useMemo(
    () => groupDocumentsByCategory(requiredDocuments),
    [requiredDocuments]
  );

  // Count required vs optional
  const documentCounts = useMemo(() => {
    const required = requiredDocuments.filter(d => d.required).length;
    const optional = requiredDocuments.filter(d => !d.required).length;
    return { required, optional, total: required + optional };
  }, [requiredDocuments]);

  // Get documents for a specific stage
  const getDocumentsForStage = (stageId) => {
    return requiredDocuments.filter(d => d.stage === stageId);
  };

  return {
    requiredDocuments,
    documentsByCategory,
    documentCounts,
    getDocumentsForStage,
    getCategoryLabel,
  };
};

export default useDocumentChecklist;
