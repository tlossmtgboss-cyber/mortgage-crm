/**
 * Application Reducer
 * Handles all state changes for the mortgage application flow
 */

// Bump this when formData shape changes (new fields, renames, etc.)
// Saved states with a different version will have formData merged with current defaults.
export const SCHEMA_VERSION = 2;

// Action Types
export const ActionTypes = {
  // Form Data
  SET_FIELD: 'SET_FIELD',
  SET_FIELDS: 'SET_FIELDS',
  SET_BORROWER_FIELD: 'SET_BORROWER_FIELD',

  // Navigation
  SET_STAGE: 'SET_STAGE',
  NEXT_QUESTION: 'NEXT_QUESTION',
  PREV_QUESTION: 'PREV_QUESTION',
  SET_QUESTION_INDEX: 'SET_QUESTION_INDEX',

  // Multi-borrower
  SET_BORROWER_INDEX: 'SET_BORROWER_INDEX',
  ADD_BORROWER: 'ADD_BORROWER',
  REMOVE_BORROWER: 'REMOVE_BORROWER',

  // Validation
  SET_VALIDATION_ERROR: 'SET_VALIDATION_ERROR',
  CLEAR_VALIDATION_ERROR: 'CLEAR_VALIDATION_ERROR',
  CLEAR_ALL_ERRORS: 'CLEAR_ALL_ERRORS',

  // Stage Completion
  MARK_STAGE_COMPLETE: 'MARK_STAGE_COMPLETE',
  MARK_STAGE_INCOMPLETE: 'MARK_STAGE_INCOMPLETE',

  // Submission
  SET_SUBMITTING: 'SET_SUBMITTING',
  SET_SUBMITTED: 'SET_SUBMITTED',
  SET_SUBMISSION_ERROR: 'SET_SUBMISSION_ERROR',

  // Persistence
  RESTORE_STATE: 'RESTORE_STATE',
  SET_LAST_SAVED: 'SET_LAST_SAVED',

  // Reset
  RESET_APPLICATION: 'RESET_APPLICATION',
};

// Initial State Factory
export const createInitialState = (applicationType = 'purchase') => ({
  // Schema version for restore compatibility
  schemaVersion: SCHEMA_VERSION,

  // Application metadata
  applicationType, // 'purchase' or 'refinance'
  applicationId: null,
  workspaceSlug: null,

  // Navigation state
  currentStage: 'about_you',
  currentQuestionIndex: 0,
  currentBorrowerIndex: 0, // 0 = primary borrower

  // Form data - organized by stage
  formData: {
    // About You stage
    veteran_status: null,
    active_duty: null,
    va_benefit_used: null,
    borrower_count: null,

    // Primary borrower info
    borrowers: [{
      first_name: '',
      middle_name: '',
      last_name: '',
      suffix: '',
      email: '',
      phone: '',
      date_of_birth: '',
      ssn: '',
      citizenship: null,
      marital_status: null,
      dependents_count: null,
      dependents_ages: '',
      // Residence history
      current_address: null,
      current_address_street: '',
      current_address_unit: '',
      current_address_city: '',
      current_address_state: '',
      current_address_zip: '',
      current_residence_type: null,
      current_monthly_payment: '',
      time_at_current_address_years: '',
      time_at_current_address_months: '',
      previous_addresses: [],
    }],

    // New Home / Property stage
    property_type: null,
    property_use: null,
    property_address: null,
    property_street: '',
    property_unit: '',
    property_city: '',
    property_state: '',
    property_zip: '',
    purchase_price: '',
    down_payment: '',
    down_payment_percent: '',

    // Income stage
    employment_status: null,
    employer_name: '',
    employer_address: '',
    employer_city: '',
    employer_state: '',
    employer_zip: '',
    employer_phone: '',
    job_title: '',
    years_in_profession: '',
    years_at_job: '',
    months_at_job: '',
    annual_base_income: '',
    has_overtime: false,
    overtime_amount: '',
    has_bonus: false,
    bonus_amount: '',
    has_commission: false,
    commission_amount: '',
    is_self_employed: false,
    business_name: '',
    business_type: null,
    business_ownership_percent: '',

    // Assets stage
    checking_balance: '',
    savings_balance: '',
    retirement_balance: '',
    investment_balance: '',
    other_assets: '',
    down_payment_source: null,
    has_gift_funds: false,
    gift_amount: '',
    gift_donor_name: '',
    gift_donor_relationship: null,

    // Real Estate Owned stage
    owns_other_property: false,
    other_properties: [],

    // Background / Declarations stage
    has_outstanding_judgments: null,
    has_bankruptcy: null,
    bankruptcy_type: null,
    bankruptcy_discharge_date: '',
    has_foreclosure: null,
    foreclosure_date: '',
    has_lawsuit: null,
    has_delinquent_debt: null,
    has_alimony_obligation: null,
    alimony_monthly_amount: '',
    is_co_signer: null,
    is_us_citizen: null,
    has_ownership_interest: null,

    // Government Monitoring (HMDA)
    ethnicity: null,
    race: [],
    sex: null,

    // Schedule stage
    preferred_contact_time: null,
    scheduled_appointment: null,

    // Authorizations stage
    econsent_agreed: false,
    econsent_timestamp: null,
    credit_auth_agreed: false,
    credit_auth_timestamp: null,

    // Refinance-specific
    current_lender: '',
    current_loan_balance: '',
    current_interest_rate: '',
    current_mortgage_payment: '',
    current_loan_type: null,
    refinance_purpose: null,
    cash_out_amount: '',
    has_second_mortgage: false,
    second_mortgage_balance: '',
    second_mortgage_payment: '',

    // Realtor info
    has_realtor: null,
    realtor_name: '',
    realtor_email: '',
    realtor_phone: '',
    realtor_company: '',
  },

  // Validation state
  validationErrors: {},

  // Stage completion tracking
  completedStages: [],

  // Submission state
  isSubmitting: false,
  isSubmitted: false,
  submissionError: null,
  submissionResult: null,

  // Persistence state
  lastSavedAt: null,
  isDirty: false,
});

// Reducer function
export function applicationReducer(state, action) {
  switch (action.type) {
    // Form Data Actions
    case ActionTypes.SET_FIELD:
      return {
        ...state,
        formData: {
          ...state.formData,
          [action.field]: action.value,
        },
        isDirty: true,
      };

    case ActionTypes.SET_FIELDS:
      return {
        ...state,
        formData: {
          ...state.formData,
          ...action.fields,
        },
        isDirty: true,
      };

    case ActionTypes.SET_BORROWER_FIELD: {
      const borrowers = [...state.formData.borrowers];
      const borrowerIndex = action.borrowerIndex ?? state.currentBorrowerIndex;

      // Fill any gaps with default borrower objects to prevent sparse arrays
      while (borrowers.length <= borrowerIndex) {
        borrowers.push({
          first_name: '',
          middle_name: '',
          last_name: '',
          suffix: '',
          email: '',
          phone: '',
          date_of_birth: '',
          ssn: '',
          citizenship: null,
          marital_status: null,
          dependents_count: null,
          dependents_ages: '',
          current_address: null,
          current_address_street: '',
          current_address_unit: '',
          current_address_city: '',
          current_address_state: '',
          current_address_zip: '',
          current_residence_type: null,
          current_monthly_payment: '',
          time_at_current_address_years: '',
          time_at_current_address_months: '',
          previous_addresses: [],
        });
      }

      borrowers[borrowerIndex] = {
        ...borrowers[borrowerIndex],
        [action.field]: action.value,
      };

      return {
        ...state,
        formData: {
          ...state.formData,
          borrowers,
        },
        isDirty: true,
      };
    }

    // Navigation Actions
    case ActionTypes.SET_STAGE:
      return {
        ...state,
        currentStage: action.stage,
        currentQuestionIndex: 0,
      };

    case ActionTypes.NEXT_QUESTION:
      return {
        ...state,
        currentQuestionIndex: state.currentQuestionIndex + 1,
      };

    case ActionTypes.PREV_QUESTION:
      return {
        ...state,
        currentQuestionIndex: Math.max(0, state.currentQuestionIndex - 1),
      };

    case ActionTypes.SET_QUESTION_INDEX:
      return {
        ...state,
        currentQuestionIndex: action.index,
      };

    // Multi-borrower Actions
    case ActionTypes.SET_BORROWER_INDEX:
      return {
        ...state,
        currentBorrowerIndex: action.index,
      };

    case ActionTypes.ADD_BORROWER: {
      const newBorrower = {
        first_name: '',
        middle_name: '',
        last_name: '',
        suffix: '',
        email: '',
        phone: '',
        date_of_birth: '',
        ssn: '',
        citizenship: null,
        marital_status: null,
        dependents_count: null,
        dependents_ages: '',
        current_address: null,
        current_address_street: '',
        current_address_unit: '',
        current_address_city: '',
        current_address_state: '',
        current_address_zip: '',
        current_residence_type: null,
        current_monthly_payment: '',
        time_at_current_address_years: '',
        time_at_current_address_months: '',
        previous_addresses: [],
      };

      return {
        ...state,
        formData: {
          ...state.formData,
          borrowers: [...state.formData.borrowers, newBorrower],
        },
        isDirty: true,
      };
    }

    case ActionTypes.REMOVE_BORROWER: {
      const borrowers = state.formData.borrowers.filter((_, i) => i !== action.index);
      return {
        ...state,
        formData: {
          ...state.formData,
          borrowers,
        },
        currentBorrowerIndex: Math.min(state.currentBorrowerIndex, borrowers.length - 1),
        isDirty: true,
      };
    }

    // Validation Actions
    case ActionTypes.SET_VALIDATION_ERROR:
      return {
        ...state,
        validationErrors: {
          ...state.validationErrors,
          [action.field]: action.error,
        },
      };

    case ActionTypes.CLEAR_VALIDATION_ERROR: {
      const { [action.field]: _, ...remainingErrors } = state.validationErrors;
      return {
        ...state,
        validationErrors: remainingErrors,
      };
    }

    case ActionTypes.CLEAR_ALL_ERRORS:
      return {
        ...state,
        validationErrors: {},
      };

    // Stage Completion Actions
    case ActionTypes.MARK_STAGE_COMPLETE:
      if (state.completedStages.includes(action.stage)) {
        return state;
      }
      return {
        ...state,
        completedStages: [...state.completedStages, action.stage],
      };

    case ActionTypes.MARK_STAGE_INCOMPLETE:
      return {
        ...state,
        completedStages: state.completedStages.filter(s => s !== action.stage),
      };

    // Submission Actions
    case ActionTypes.SET_SUBMITTING:
      return {
        ...state,
        isSubmitting: action.value,
        submissionError: null,
      };

    case ActionTypes.SET_SUBMITTED:
      return {
        ...state,
        isSubmitting: false,
        isSubmitted: true,
        submissionResult: action.result,
      };

    case ActionTypes.SET_SUBMISSION_ERROR:
      return {
        ...state,
        isSubmitting: false,
        submissionError: action.error,
      };

    // Persistence Actions
    case ActionTypes.RESTORE_STATE: {
      const saved = action.savedState || {};
      const defaults = createInitialState(state.applicationType);

      // Merge saved formData with current defaults so new fields always exist
      const mergedFormData = {
        ...defaults.formData,
        ...(saved.formData || {}),
      };

      // Merge each borrower with default borrower shape
      if (mergedFormData.borrowers && Array.isArray(mergedFormData.borrowers)) {
        const defaultBorrower = defaults.formData.borrowers[0];
        mergedFormData.borrowers = mergedFormData.borrowers.map(b =>
          b ? { ...defaultBorrower, ...b } : { ...defaultBorrower }
        );
      }

      // Migrate renamed fields from older schema versions
      if (!saved.schemaVersion || saved.schemaVersion < 2) {
        // v1→v2: current_monthly_payment renamed to current_mortgage_payment (refinance)
        if (mergedFormData.current_monthly_payment !== undefined
            && mergedFormData.current_mortgage_payment === '') {
          mergedFormData.current_mortgage_payment = mergedFormData.current_monthly_payment;
        }
        delete mergedFormData.current_monthly_payment;
      }

      return {
        ...state,
        ...saved,
        schemaVersion: SCHEMA_VERSION,
        formData: mergedFormData,
        isDirty: false,
      };
    }

    case ActionTypes.SET_LAST_SAVED:
      return {
        ...state,
        lastSavedAt: action.timestamp,
        isDirty: false,
      };

    // Reset Action
    case ActionTypes.RESET_APPLICATION:
      return createInitialState(state.applicationType);

    default:
      console.warn(`Unknown action type: ${action.type}`);
      return state;
  }
}

export default applicationReducer;
