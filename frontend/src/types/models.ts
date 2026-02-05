/**
 * Core domain models matching backend database models
 *
 * These types represent the main entities in the mortgage CRM system.
 * Keep in sync with backend/database/models/ and backend/database/enums.py
 */

// ============================================================================
// ENUMS - Lead & Loan Pipeline
// ============================================================================

export type LeadStage =
  | 'New'
  | 'Attempted Contact'
  | 'Prospect'
  | 'Application'
  | 'APPLICATION_STARTED'
  | 'Document Fulfillment'
  | 'Pre-Qualified'
  | 'Pre-Approved'
  | 'Under Contract'
  | 'Long-Term Nurture'
  | 'Closed'
  | 'AMR'
  | 'Referral Source'
  | 'Withdrawn'
  | 'Does Not Qualify'
  | 'Disclosed';

export type LoanStage =
  | 'APPLICATION'
  | 'DISCLOSED'
  | 'PROCESSING'
  | 'SUBMITTED'
  | 'UNDERWRITING'
  | 'UW_RECEIVED'
  | 'CONDITIONAL_APPROVAL'
  | 'APPROVED'
  | 'SUSPENDED'
  | 'CTC'
  | 'CLEAR_TO_CLOSE'
  | 'CLOSING'
  | 'DOCS'
  | 'DOCS_OUT'
  | 'FUNDED'
  | 'CANCELLED'
  | 'DENIED'
  | 'DEAD'
  | 'NURTURE'
  | 'WITHDRAWN'
  | 'DOES_NOT_QUALIFY';

export type RateLockStatus =
  | 'Not Eligible'
  | 'Eligible - No Lock'
  | 'Locked'
  | 'Float Monitoring'
  | 'Lock Expiring'
  | 'Lock Extended'
  | 'Lock Expired';

export type RateLockRecommendation =
  | 'Lock Now'
  | 'Float and Monitor'
  | 'Extend Lock'
  | 'Relock'
  | 'Explore Float-Down';

export type BuyingTimelineCategory =
  | 'Platinum'
  | 'Gold'
  | 'Silver'
  | 'Green';

export type BorrowerRiskProfile =
  | 'Safety First'
  | 'Balanced'
  | 'Aggressive';

export type UserRole =
  | 'admin'
  | 'site_admin'
  | 'leadership'
  | 'management'
  | 'sales'
  | 'processing'
  | 'operations'
  | 'loan_officer';

export type ActivityType =
  | 'Email'
  | 'Call'
  | 'Meeting'
  | 'Note'
  | 'SMS'
  | 'Document';

// ============================================================================
// CORE MODELS
// ============================================================================

export interface Organization {
  id: number;
  name: string;
  slug: string | null;
  domain: string | null;
  settings: Record<string, unknown>;
  subscription_tier: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Branch {
  id: number;
  name: string;
  company: string | null;
  nmls_id: string | null;
  organization_id: number | null;
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  first_name: string | null;
  last_name: string | null;
  full_name: string;
  role: string;
  permission_role: UserRole;
  branch_id: number | null;
  organization_id: number | null;
  is_active: boolean;
  email_verified: boolean;
  onboarding_completed: boolean;
  phone: string | null;
  nmls_number: string | null;
  nmls_id: string | null;
  business_address: string | null;
  current_role: string | null;
  business_hours: Record<string, unknown> | null;
  slug: string | null;
  company_logo_url: string | null;
  headshot_url: string | null;
  title: string | null;
  team_name: string | null;
  timezone: string;
  last_activity_at: string | null;
  created_at: string;
  user_metadata: Record<string, unknown> | null;
}

export interface Lead {
  id: number;
  organization_id: number | null;
  name: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  phone: string | null;

  // Co-applicant
  co_applicant_name: string | null;
  co_applicant_email: string | null;
  co_applicant_phone: string | null;

  // Communication
  preferred_communication: string | null;

  // Pipeline status
  stage: LeadStage;
  source: string | null;
  organization_code: string | null;
  referral_partner_id: number | null;

  // AI scoring
  ai_score: number;
  sentiment: string;
  next_action: string | null;

  // Loan qualification
  loan_type: string | null;
  preapproval_amount: number | null;
  credit_score: number | null;
  debt_to_income: number | null;

  // Assignment
  owner_id: number | null;
  last_contact: string | null;
  loan_number: string | null;
  notes: string | null;

  // Property Information
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  property_type: string | null;
  property_value: number | null;
  down_payment: number | null;
  property_address: string | null;

  // Financial Information
  employment_status: string | null;
  annual_income: number | null;
  monthly_debts: number | null;
  first_time_buyer: boolean;

  // Loan Details
  loan_amount: number | null;
  interest_rate: number | null;
  loan_term: number | null;
  apr: number | null;
  points: number | null;
  lock_date: string | null;
  lock_expiration: string | null;
  closing_date: string | null;
  lender: string | null;
  loan_officer: string | null;
  processor: string | null;
  underwriter: string | null;
  appraisal_value: number | null;
  ltv: number | null;
  cltv: number | null;
  dti: number | null;
  dti_front: number | null;
  dti_back: number | null;
  program: string | null;
  status_date: string | null;

  // Rate Lock Intelligence
  buying_timeline_category: BuyingTimelineCategory | null;
  borrower_risk_profile: BorrowerRiskProfile | null;
  target_payment: number | null;
  expected_purchase_date: string | null;

  // Referral Fields
  referral_score: number;
  referral_source_score: number;
  employment_referral_flag: boolean;
  manager_flag: boolean;
  employees_managed: number;
  leadership_level: string | null;
  company_size: number | null;
  employer_name: string | null;
  industry: string | null;
  circle_of_cash_flow_map: Record<string, unknown> | null;

  // Workflow tracking
  current_workflow_id: string | null;
  workflow_day: number;
  last_workflow_action: string | null;
  nurture_month: number;
  stage_changed_at: string | null;

  // Salesforce Integration
  salesforce_id: string | null;
  meta_data: Record<string, unknown> | null;
  user_metadata: Record<string, unknown> | null;

  // Timestamps
  created_at: string;
  updated_at: string;
}

export interface Loan {
  id: number;
  organization_id: number | null;
  loan_number: string;

  // Borrower info
  borrower_name: string;
  borrower_email: string | null;
  borrower_phone: string | null;
  preferred_communication: string | null;
  coborrower_name: string | null;
  co_borrower_email: string | null;

  // Pipeline status
  stage: LoanStage | string;
  program: string | null;
  loan_type: string | null;

  // Financials
  amount: number;
  purchase_price: number | null;
  down_payment: number | null;
  rate: number | null;
  term: number;

  // Property
  property_address: string | null;
  property_city: string | null;
  property_state: string | null;
  property_zip: string | null;
  property_type: string | null;
  occupancy_type: string | null;

  // Key dates
  lock_date: string | null;
  closing_date: string | null;
  funded_date: string | null;
  lock_expiration_date: string | null;

  // Team
  loan_officer_id: number | null;
  loan_officer_name: string | null;
  loan_officer_email: string | null;
  processor: string | null;
  processor_email: string | null;
  underwriter: string | null;
  underwriter_email: string | null;
  closer: string | null;
  closer_email: string | null;
  realtor_agent: string | null;
  title_company: string | null;
  lender: string | null;

  // SLA tracking
  days_in_stage: number;
  sla_status: string;
  milestones: Record<string, unknown> | null;
  ai_insights: string | null;
  predicted_close_date: string | null;
  risk_score: number;

  // Rate lock fields
  rate_lock_status: RateLockStatus;
  rate_lock_recommendation: RateLockRecommendation | null;
  lock_term_days: number | null;
  float_down_available: boolean;
  float_down_terms: string | null;
  extension_cost_estimate: number | null;
  volatility_score: number;
  borrower_risk_profile: BorrowerRiskProfile | null;
  lock_score: number | null;
  lock_decision_date: string | null;
  lock_decision_notes: string | null;
  last_rate_check: string | null;
  rate_lock_history: Record<string, unknown>[] | null;

  // Appraisal tracking
  appraisal_ordered_date: string | null;
  appraisal_scheduled_date: string | null;
  appraisal_completed_date: string | null;
  appraisal_value: number | null;
  appraisal_received_date: string | null;

  // Workflow tracking
  current_workflow_id: string | null;
  last_workflow_action: string | null;
  stage_changed_at: string | null;

  // Timestamps
  created_at: string;
  updated_at: string;

  // Metadata
  user_metadata: Record<string, unknown> | null;
}

export interface Activity {
  id: number;
  type: ActivityType;
  subject: string | null;
  description: string | null;
  lead_id: number | null;
  loan_id: number | null;
  user_id: number | null;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

export interface ReferralPartner {
  id: number;
  name: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  type: string | null;
  notes: string | null;
  organization_id: number | null;
  owner_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  due_date: string | null;
  assigned_to_id: number | null;
  lead_id: number | null;
  loan_id: number | null;
  created_by_id: number | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}
