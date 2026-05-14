/**
 * Purchase Application - Dynamic Document Requirements
 *
 * Generates personalized document checklist based on user's declarations,
 * assets, profile, income, and co-borrower data. Uses date-based logic
 * for tax return requirements (before/after Jan 28, Apr 15).
 *
 * URLA compliance: All documents align with Uniform Residential Loan
 * Application requirements for home purchase transactions.
 */

export const getRequiredDocuments = (
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
  if (declarations.citizenship_status) {
    docs.push({
      id: 'id',
      name: `${borrowerFirstName}'s Government ID`,
      description: "Driver's license or passport",
      category: 'identity',
      stage: 'declarations'
    });
  }

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
  const jan28 = new Date(currentYear, 0, 28);
  const isBeforeJan28 = today < jan28;

  if (isSelfEmployed) {
    const businessName = declarations.business_name?.trim() || 'your business';

    if (maximizesDeductions) {
      docs.push({
        id: 'business_bank_statements',
        name: `${borrowerFirstName}'s Business Bank Statements`,
        description: `12 consecutive months of bank statements for ${businessName}`,
        category: 'income',
        stage: 'income'
      });
    } else {
      if (isBeforeJan28) {
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

  // === ASSET DOCUMENTS ===
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
    docs.push({
      id: 'coborrower_id',
      name: `${coBorrowerFirstName}'s Government ID`,
      description: `${coBorrowerFirstName}'s driver's license or passport`,
      category: 'identity',
      stage: 'profile'
    });

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
