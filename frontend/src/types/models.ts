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

  // Milestone state (workflow engine)
  current_milestone_status: string | null;
  current_milestone_entered_at: string | null;

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

  // Milestone state (workflow engine)
  current_milestone_status: string | null;
  current_milestone_entered_at: string | null;

  // MUM
  mum_date: string | null;

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

// ============================================================================
// WORKFLOW & SLA TYPES
// ============================================================================

export type SLAStatusValue =
  | 'ON_TRACK'
  | 'APPROACHING'
  | 'OVERDUE'
  | 'COMPLETED'
  | 'NO_DATE';

export type WorkflowTaskType =
  | 'phone'
  | 'phone_am'
  | 'phone_pm'
  | 'text'
  | 'text_am'
  | 'text_pm'
  | 'email'
  | 'referral_partner'
  | 'ai'
  | 'internal';

export type WorkflowRoute =
  | 'task_list'
  | 'dialer_queue'
  | 'ai_autonomous'
  | 'email_automation'
  | 'sms_automation';

export type WorkflowTaskStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'archived'
  | 'cancelled'
  | 'skipped';

/** Important Dates on a loan/lead — source of truth for workflow triggers */
export interface ImportantDates {
  // Lead Stage
  lead_received_date: string | null;
  first_contact_attempt_date: string | null;
  first_contact_successful_date: string | null;
  lead_qualification_date: string | null;
  application_started_date: string | null;
  application_completed_date: string | null;

  // Active Loan Stage
  prospect_date: string | null;
  application_date: string | null;
  le_pending_date: string | null;
  credit_only_date: string | null;
  file_received_date: string | null;
  preapproval_date: string | null;
  appraisal_ordered_date: string | null;
  appraisal_received_date: string | null;
  title_ordered_date: string | null;
  title_received_date: string | null;
  uw_received_date: string | null;
  conditional_approval_date: string | null;
  conditions_for_review_date: string | null;
  suspended_date: string | null;
  loan_approved_date: string | null;
  clear_to_close_date: string | null;
  cd_requested_date: string | null;
  cd_sent_to_borrower_date: string | null;
  cd_acknowledged_date: string | null;
  docs_ordered_date: string | null;
  docs_out_date: string | null;
  scheduled_closing_date: string | null;
  scheduled_funding_date: string | null;
  funded_date: string | null;
  mum_date: string | null;

  // Current state
  current_milestone_status: string | null;
  current_milestone_entered_at: string | null;
}

/** SLA status for a single milestone */
export interface SLAMilestoneStatus {
  milestone_type: string;
  started_at: string | null;
  target_deadline: string | null;
  days_elapsed: number;
  target_days: number;
  days_remaining: number;
  status: SLAStatusValue;
  percentage_complete: number;
  needs_proactive_task: boolean;
  needs_overdue_task: boolean;
}

/** A workflow-generated task instance */
export interface WorkflowTask extends Task {
  workflow_instance_id: number | null;
  day_config_id: number | null;
  task_type: WorkflowTaskType;
  assigned_role: string | null;
  routed_to: WorkflowRoute;
  day_number: number;
  task_group_key: string | null;
  archived_at: string | null;
  archive_reason: string | null;
  ai_confidence: number | null;
  ai_auto_completed: boolean;
  // Display context
  workflow_name: string | null;
  workflow_color: string | null;
  client_name: string | null;
}

/** A milestone history entry (audit trail) */
export interface MilestoneHistoryEntry {
  id: number;
  loan_id: number | null;
  lead_id: number | null;
  milestone_type: string;
  started_at: string;
  completed_at: string | null;
  target_deadline: string | null;
  sla_target_days: number | null;
  actual_days: number | null;
  sla_status: string;
  triggered_by: string | null;
  triggered_by_user_id: number | null;
  trigger_notes: string | null;
  previous_milestone_type: string | null;
}
