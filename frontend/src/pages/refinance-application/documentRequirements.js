/**
 * Refinance Application - Dynamic Document Requirements
 *
 * Generates personalized document checklist based on user's declarations,
 * assets, profile, income, and co-borrower data. Uses date-based logic
 * for tax return requirements (before/after Jan 28).
 *
 * Key differences from purchase:
 * - No gift funds requirement
 * - Cash-out refinance triggers bank statement requirement
 * - Assets stage unlocks with income (not separate)
 * - Rental property docs for investment property refinances
 * - Always requires government ID (not gated behind citizenship question)
 *
 * URLA compliance: All documents align with Uniform Residential Loan
 * Application requirements for refinance transactions.
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
  const hasCoBorrower = ['2', '3', '4+'].includes(declarations.borrower_count);
  const isCashOut = declarations.refi_goal === 'cash_out';
  const maximizesDeductions = declarations.write_off_expenses === 'yes';

  // Parse asset values (for refinance, may come from income stage)
  const hasCheckingOrSavings = (parseFloat(assetData.checking) || 0) > 0 || (parseFloat(assetData.savings) || 0) > 0;
  const hasInvestmentOrRetirement = (parseFloat(assetData.investments) || 0) > 0 || (parseFloat(assetData.retirement) || 0) > 0;

  // Get borrower names for personalization
  const borrowerFirstName = profileData?.firstName?.trim() || 'Primary Borrower';
  const coBorrowerFirstName = coBorrowerData?.firstName?.trim() || 'Co-Borrower';

  // Get employer names from income data
  const primaryEmployer = incomeData?.employerName?.trim() || null;
  const coBorrowerEmployer = coBorrowerIncomeData?.employerName?.trim() || null;

  // Current year for document labels
  const currentYear = new Date().getFullYear();
  const priorYear = currentYear - 1;
  const twoYearsAgo = currentYear - 2;

  // === IDENTITY DOCUMENTS ===
  // Always require government ID (driver's license or passport)
  docs.push({
    id: 'id',
    name: `${borrowerFirstName}'s Government ID`,
    description: "Driver's license or passport",
    category: 'identity',
    stage: 'declarations'
  });

  // Citizenship-based documents
  if (declarations.citizenship_status === 'permanent_resident') {
    docs.push({
      id: 'green_card',
      name: 'Green Card',
      description: 'Unexpired Permanent Resident Card',
      category: 'identity',
      stage: 'declarations'
    });
  }
  if (declarations.citizenship_status === 'non_permanent_resident' || declarations.citizenship_status === 'non_resident') {
    docs.push({
      id: 'visa_docs',
      name: 'Visa Documents',
      description: 'Current visa and work authorization',
      category: 'identity',
      stage: 'declarations'
    });
  }

  // === INCOME DOCUMENTS ===
  if (isSelfEmployed) {
    // Date-based logic for self-employment documents
    const today = new Date();
    const jan28 = new Date(currentYear, 0, 28); // January 28th
    const isBeforeJan28 = today < jan28;

    if (maximizesDeductions) {
      // Heavy deductions - use bank statement program instead of tax returns
      docs.push({
        id: 'business_bank_statements',
        name: 'Business Bank Statements',
        description: '12 months of business bank statements',
        category: 'income',
        stage: 'income'
      });
    } else {
      // Standard self-employed documentation
      if (isBeforeJan28) {
        // Before Jan 28 - prior year taxes can't be filed yet, need P&L
        docs.push({
          id: 'tax_returns',
          name: 'Tax Returns',
          description: `Personal returns (${priorYear - 1})`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns',
          name: 'Business Tax Returns',
          description: `Business returns (${priorYear - 1})`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'profit_loss',
          name: 'Profit & Loss Statement',
          description: `${priorYear} P&L (signed by applicant)`,
          category: 'income',
          stage: 'income'
        });
      } else if (declarations.prior_year_taxes_filed === 'yes') {
        // After Jan 28 and taxes filed - request full tax returns
        docs.push({
          id: 'tax_returns',
          name: 'Tax Returns',
          description: 'Personal returns (last 2 years)',
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns',
          name: 'Business Tax Returns',
          description: 'Business returns (last 2 years)',
          category: 'income',
          stage: 'income'
        });
      } else {
        // After Jan 28 but taxes not filed - need prior year P&L
        docs.push({
          id: 'tax_returns',
          name: 'Tax Returns',
          description: `Personal returns (${priorYear - 1})`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'business_tax_returns',
          name: 'Business Tax Returns',
          description: `Business returns (${priorYear - 1})`,
          category: 'income',
          stage: 'income'
        });
        docs.push({
          id: 'profit_loss',
          name: 'Profit & Loss Statement',
          description: `${priorYear} P&L (signed by applicant)`,
          category: 'income',
          stage: 'income'
        });
      }
    }

    // Articles of Incorporation for S-Corp or C-Corp
    if (declarations.business_type === 's_corp' || declarations.business_type === 'c_corp') {
      docs.push({
        id: 'articles_incorporation',
        name: 'Articles of Incorporation',
        description: 'Corporate formation documents',
        category: 'income',
        stage: 'income'
      });
    }
  } else {
    // W-2 employee - Personalized with borrower name and employer
    const employerLabel = primaryEmployer ? ` from ${primaryEmployer}` : '';
    docs.push({
      id: 'paystubs',
      name: `${borrowerFirstName}'s Pay Stubs${employerLabel}`,
      description: 'Last 30 days (most recent)',
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'w2_current',
      name: `${borrowerFirstName}'s ${priorYear} W-2${employerLabel}`,
      description: `${priorYear} W-2 from employer`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'w2_prior',
      name: `${borrowerFirstName}'s ${twoYearsAgo} W-2${employerLabel}`,
      description: `${twoYearsAgo} W-2 from employer`,
      category: 'income',
      stage: 'income'
    });
  }

  // === DIVORCE / CHILD SUPPORT DOCUMENTS ===
  if ((declarations.marital_status === 'divorced' || declarations.marital_status === 'separated') &&
      declarations.child_support_alimony && declarations.child_support_alimony !== 'neither') {
    docs.push({
      id: 'divorce_decree',
      name: 'Divorce Decree',
      description: 'Final divorce decree',
      category: 'income',
      stage: 'declarations'
    });
    docs.push({
      id: 'property_settlement',
      name: 'Property Settlement Agreement',
      description: 'Marital settlement agreement',
      category: 'income',
      stage: 'declarations'
    });
  }

  // === VETERAN DOCUMENTS ===
  if (declarations.veteran === 'yes' || declarations.veteran === 'active' || declarations.veteran === 'spouse') {
    docs.push({
      id: 'va_coe',
      name: 'Certificate of Eligibility',
      description: 'VA Certificate of Eligibility (COE)',
      category: 'identity',
      stage: 'declarations'
    });
  }
  if (declarations.va_disability === 'pending') {
    docs.push({
      id: 'va_pending_claim',
      name: 'VA Pending Claim',
      description: 'Pending VA disability claim paperwork',
      category: 'identity',
      stage: 'declarations'
    });
  }

  // === IRS DOCUMENTS ===
  if (declarations.irs_balance_owed === 'payment_plan') {
    docs.push({
      id: 'irs_payment_arrangement',
      name: 'IRS Payment Arrangement',
      description: 'IRS installment agreement letter',
      category: 'income',
      stage: 'declarations'
    });
  } else if (declarations.irs_balance_owed === 'yes') {
    docs.push({
      id: 'irs_payoff',
      name: 'IRS Payoff Statement',
      description: 'Current IRS balance and payoff amount',
      category: 'income',
      stage: 'declarations'
    });
  }

  // === RENTAL PROPERTY DOCUMENTS (for investment properties being refinanced) ===
  if (declarations.property_use === 'investment' || declarations.has_rental_income === 'yes') {
    docs.push({
      id: 'rental_tax_returns',
      name: 'Tax Returns with Schedule E',
      description: 'Most recent tax returns showing rental income',
      category: 'income',
      stage: 'declarations'
    });
    docs.push({
      id: 'lease_agreement',
      name: 'Lease Agreement',
      description: 'Current signed lease agreement',
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
      name: label,
      description: 'Statement for recently opened account',
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
          name: 'Bankruptcy Documents',
          description: 'Chapter 7 discharge papers',
          category: 'identity',
          stage: 'declarations'
        });
      }
    } else if (declarations.bankruptcy_type === 'chapter_13') {
      if (declarations.chapter_13_status === 'active_paying') {
        docs.push({
          id: 'ch13_payment_history',
          name: 'Payment History',
          description: 'Chapter 13 trustee payment history',
          category: 'identity',
          stage: 'declarations'
        });
        docs.push({
          id: 'ch13_court_approval',
          name: 'Court Approval Letter',
          description: 'Court approval for new mortgage',
          category: 'identity',
          stage: 'declarations'
        });
      } else {
        docs.push({
          id: 'bankruptcy_discharge',
          name: 'Discharge Paperwork',
          description: 'Chapter 13 discharge documents',
          category: 'identity',
          stage: 'declarations'
        });
      }
    } else if (declarations.bankruptcy_type === 'chapter_12') {
      docs.push({
        id: 'ch12_payment_history',
        name: '12-Month Payment History',
        description: 'Chapter 12 payment history',
        category: 'identity',
        stage: 'declarations'
      });
      docs.push({
        id: 'ch12_court_approval',
        name: 'Court Approval Letter',
        description: 'Court approval letter for financing',
        category: 'identity',
        stage: 'declarations'
      });
    }
  }

  // === ASSET DOCUMENTS ===
  // For cash-out refinances or if user has entered asset values
  if (isCashOut || hasCheckingOrSavings) {
    docs.push({
      id: 'bank_statements',
      name: 'Bank Statements',
      description: 'Last 2 months (checking/savings)',
      category: 'assets',
      stage: 'income'
    });
  }
  if (hasInvestmentOrRetirement) {
    docs.push({
      id: 'investment_statements',
      name: 'Investment Statements',
      description: 'Retirement/brokerage accounts',
      category: 'assets',
      stage: 'income'
    });
  }

  // === CO-BORROWER DOCUMENTS ===
  if (hasCoBorrower) {
    docs.push({
      id: 'coborrower_id',
      name: `${coBorrowerFirstName}'s Government ID`,
      description: "Driver's license or passport",
      category: 'identity',
      stage: 'profile'
    });
    // Co-borrower income documents with personalized labels
    const coBorrowerEmployerLabel = coBorrowerEmployer ? ` from ${coBorrowerEmployer}` : '';
    docs.push({
      id: 'coborrower_paystubs',
      name: `${coBorrowerFirstName}'s Pay Stubs${coBorrowerEmployerLabel}`,
      description: 'Last 30 days (most recent)',
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'coborrower_w2_current',
      name: `${coBorrowerFirstName}'s ${priorYear} W-2${coBorrowerEmployerLabel}`,
      description: `${priorYear} W-2 from employer`,
      category: 'income',
      stage: 'income'
    });
    docs.push({
      id: 'coborrower_w2_prior',
      name: `${coBorrowerFirstName}'s ${twoYearsAgo} W-2${coBorrowerEmployerLabel}`,
      description: `${twoYearsAgo} W-2 from employer`,
      category: 'income',
      stage: 'income'
    });
  }

  return docs;
};
