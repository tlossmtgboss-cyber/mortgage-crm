/**
 * Shared helper functions for mortgage application forms.
 * Contains question navigation, progress calculation, and form utility functions.
 */

/**
 * Check if a declaration question should be shown based on conditions.
 * @param {Object} question - Question definition with optional showIf/hideIf
 * @param {Object} currentDeclarations - Current declaration answers
 * @returns {boolean} Whether the question should be displayed
 */
export const shouldShowQuestion = (question, currentDeclarations) => {
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
};

/**
 * Get filtered questions based on current declarations.
 * @param {Array} enabledQuestions - All enabled questions
 * @param {Object} declarations - Current declaration answers
 * @returns {Array} Visible questions
 */
export const getVisibleQuestions = (enabledQuestions, declarations) => {
  return enabledQuestions.filter(q => shouldShowQuestion(q, declarations));
};

/**
 * Calculate progress percentage through the application.
 * @param {string} currentStage - Current stage ID
 * @param {number} currentQuestionIndex - Current question index (for declarations)
 * @param {Array} visibleStages - Visible stages (excluding hidden ones)
 * @param {Array} enabledQuestions - Enabled questions (for declarations progress)
 * @returns {number} Progress percentage (0-100)
 */
export const calculateProgress = (currentStage, currentQuestionIndex, visibleStages, enabledQuestions) => {
  if (currentStage === 'account') return 0;
  const stageIndex = visibleStages.findIndex(s => s.id === currentStage);
  if (stageIndex === -1) return 0;
  const stageProgress = (stageIndex / visibleStages.length) * 100;
  if (currentStage === 'declarations') {
    const questionProgress = (currentQuestionIndex / enabledQuestions.length) * (100 / visibleStages.length);
    return Math.round(stageProgress + questionProgress);
  }
  return Math.round(stageProgress);
};

/**
 * Get stage-specific micro-win messages.
 * @param {string} stageId - Completed stage ID
 * @param {Object} customMessages - Optional override messages
 * @returns {string} Micro-win message
 */
export const getStageMicroWin = (stageId, customMessages = {}) => {
  const defaults = {
    account: 'Account created!',
    declarations: 'Great start!',
    planning: 'Goals captured!',
    profile: 'Profile complete!',
    income: 'Income captured!',
    assets: 'Assets recorded!',
    property: 'Almost done!',
    goals: 'Goals set!',
    review: 'Ready to submit!',
  };
  return customMessages[stageId] || defaults[stageId] || 'Section complete!';
};

/**
 * Get enabled stages based on application configuration.
 * @param {Object} applicationConfig - Configuration loaded from backend
 * @param {Array} defaultStages - Default stage definitions
 * @returns {Array} Enabled stages
 */
export const getEnabledStages = (applicationConfig, defaultStages) => {
  if (!applicationConfig?.stages) return defaultStages;

  return applicationConfig.stages
    .filter(configStage => configStage.enabled)
    .map(configStage => {
      const originalStage = defaultStages.find(s => s.id === configStage.id);
      return originalStage ? { ...originalStage, ...configStage } : configStage;
    });
};

/**
 * Get enabled declaration questions based on application configuration.
 * @param {Object} applicationConfig - Configuration loaded from backend
 * @param {Array} defaultQuestions - Default question definitions
 * @returns {Array} Enabled questions
 */
export const getEnabledQuestions = (applicationConfig, defaultQuestions) => {
  if (!applicationConfig?.declarationQuestions) return defaultQuestions;

  const enabledIds = new Set(
    applicationConfig.declarationQuestions
      .filter(q => q.enabled)
      .map(q => q.id)
  );

  return defaultQuestions.filter(q => enabledIds.has(q.id));
};

/**
 * Build a dynamic needs/checklist from current declarations.
 * @param {Object} declarations - Current declaration answers
 * @param {string} applicationType - 'purchase' or 'refinance'
 * @returns {Array} Needs list items
 */
export const buildNeedsList = (declarations, applicationType = 'purchase') => {
  const needs = [];
  needs.push({ id: 'id', label: "Driver's license or passport", category: 'identity' });
  if (declarations.citizenship_status && declarations.citizenship_status !== 'us_citizen') {
    needs.push({ id: 'green_card', label: 'Unexpired Green Card (front & back)', category: 'identity' });
    if (declarations.citizenship_status === 'non_permanent_resident')
      needs.push({ id: 'visa_docs', label: 'Visa documentation (I-94, EAD, etc.)', category: 'identity' });
  }
  if (declarations.self_employed === 'yes' || declarations.self_employed === 'side_business') {
    needs.push({ id: 'tax_returns', label: '2 years tax returns', category: 'income' });
    needs.push({ id: 'profit_loss', label: 'Year-to-date P&L statement', category: 'income' });
    if (declarations.write_off_expenses === 'yes')
      needs.push({ id: 'business_bank_statements', label: '12 months business bank statements', category: 'income' });
  } else {
    needs.push({ id: 'paystubs', label: 'Recent pay stubs (30 days)', category: 'income' });
    needs.push({ id: 'w2', label: 'W-2s (last 2 years)', category: 'income' });
  }
  if (declarations.veteran && declarations.veteran !== 'no')
    needs.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
  if (declarations.irs_balance_owed === 'yes' || declarations.irs_balance_owed === 'payment_plan')
    needs.push({ id: 'irs_docs', label: 'IRS payment arrangement documentation', category: 'legal' });
  if (declarations.credit_application_approved === 'yes')
    needs.push({ id: 'new_account_statement', label: 'New account statement (loan/credit card)', category: 'assets' });
  needs.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });
  // Application-type-specific items
  if (applicationType === 'refinance') {
    needs.push({ id: 'mortgage_statement', label: 'Current mortgage statement', category: 'property' });
    needs.push({ id: 'hoi', label: 'Homeowners insurance declaration', category: 'property' });
    if (declarations.refi_goal === 'cash_out')
      needs.push({ id: 'home_value', label: 'Recent appraisal or home value estimate', category: 'property' });
  }
  if (applicationType === 'purchase') {
    if (declarations.gift_funds === 'yes') {
      needs.push({ id: 'gift_letter', label: 'Gift letter from donor', category: 'assets' });
      needs.push({ id: 'gift_source', label: 'Donor bank statements', category: 'assets' });
    }
    if (declarations.found_property === 'yes')
      needs.push({ id: 'purchase_contract', label: 'Purchase contract', category: 'property' });
  }
  return needs;
};

/**
 * Build portal redirect URL for post-submission redirect.
 * @param {string|null} portalUrl - Portal URL from submission response
 * @param {string} appLabel - Application type label for logging
 * @returns {string} Redirect URL
 */
export const buildRedirectUrl = (portalUrl, appLabel = 'Application') => {
  if (portalUrl) return portalUrl;

  const isProduction = window.location.hostname.includes('perenniaai.com');
  const baseHost = isProduction ? 'www.perenniaai.com' : window.location.host;
  const protocol = isProduction ? 'https' : window.location.protocol.replace(':', '');

  // Try to get the LO slug from the current URL
  const pathMatch = window.location.pathname.match(/\/(?:lo|apply)\/([^/]+)/);
  const potentialSlug = pathMatch ? pathMatch[1] : null;
  const reservedSlugs = ['purchase', 'refinance', 'login', 'start', 'oauth', 'verify'];
  const loSlug = potentialSlug && !reservedSlugs.includes(potentialSlug.toLowerCase()) ? potentialSlug : null;

  if (loSlug) {
    return `${protocol}://${baseHost}/lo/${loSlug}`;
  }

  const borrowerEmail = localStorage.getItem('borrower_email');
  if (borrowerEmail) {
    return `${protocol}://${baseHost}/borrower-portal?email=${encodeURIComponent(borrowerEmail)}&submitted=true`;
  }

  return `${protocol}://${baseHost}/application-submitted`;
};
