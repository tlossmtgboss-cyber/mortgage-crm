/**
 * API response types for the mortgage CRM backend
 *
 * These types define the shape of API responses and request payloads.
 */

import type { User, Lead, Loan, Task, Activity, ReferralPartner, Organization, Branch } from './models';

// ============================================================================
// COMMON API TYPES
// ============================================================================

/**
 * Standard API response wrapper
 */
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

/**
 * Paginated API response
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

/**
 * API error response
 */
export interface ApiError {
  detail: string;
  status_code?: number;
  errors?: Record<string, string[]>;
}

/**
 * Validation error response from FastAPI
 */
export interface ValidationError {
  detail: Array<{
    loc: (string | number)[];
    msg: string;
    type: string;
  }>;
}

// ============================================================================
// AUTH API TYPES
// ============================================================================

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RegisterRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  organization_name?: string;
}

export interface RegisterResponse {
  message: string;
  user_id: number;
  email_verification_required: boolean;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  token: string;
  new_password: string;
}

// ============================================================================
// USER API TYPES
// ============================================================================

export interface UserUpdateRequest {
  first_name?: string;
  last_name?: string;
  phone?: string;
  nmls_number?: string;
  business_address?: string;
  timezone?: string;
  headshot_url?: string;
  company_logo_url?: string;
  title?: string;
  team_name?: string;
}

export interface UserSettingsResponse {
  user: User;
  settings: Record<string, string | null>;
}

// ============================================================================
// LEAD API TYPES
// ============================================================================

export interface LeadCreateRequest {
  name: string;
  email?: string;
  phone?: string;
  first_name?: string;
  last_name?: string;
  source?: string;
  loan_type?: string;
  notes?: string;
  referral_partner_id?: number;
  property_address?: string;
  loan_amount?: number;
}

export interface LeadUpdateRequest extends Partial<LeadCreateRequest> {
  stage?: string;
  ai_score?: number;
  owner_id?: number;
}

export interface LeadListResponse extends PaginatedResponse<Lead> {}

export interface LeadFilters {
  stage?: string | string[];
  owner_id?: number;
  source?: string;
  search?: string;
  created_after?: string;
  created_before?: string;
  min_score?: number;
  max_score?: number;
}

export interface LeadStageUpdateRequest {
  stage: string;
  notes?: string;
}

export interface BulkLeadUpdateRequest {
  lead_ids: number[];
  updates: LeadUpdateRequest;
}

// ============================================================================
// LOAN API TYPES
// ============================================================================

export interface LoanCreateRequest {
  loan_number: string;
  borrower_name: string;
  borrower_email?: string;
  borrower_phone?: string;
  amount: number;
  program?: string;
  loan_type?: string;
  property_address?: string;
  loan_officer_id?: number;
}

export interface LoanUpdateRequest extends Partial<LoanCreateRequest> {
  stage?: string;
  closing_date?: string;
  lock_date?: string;
  rate?: number;
  processor?: string;
  underwriter?: string;
}

export interface LoanListResponse extends PaginatedResponse<Loan> {}

export interface LoanFilters {
  stage?: string | string[];
  loan_officer_id?: number;
  search?: string;
  closing_after?: string;
  closing_before?: string;
  funded?: boolean;
}

export interface LoanStageUpdateRequest {
  stage: string;
  notes?: string;
}

// ============================================================================
// TASK API TYPES
// ============================================================================

export interface TaskCreateRequest {
  title: string;
  description?: string;
  priority?: string;
  due_date?: string;
  assigned_to_id?: number;
  lead_id?: number;
  loan_id?: number;
}

export interface TaskUpdateRequest extends Partial<TaskCreateRequest> {
  status?: string;
  completed_at?: string;
}

export interface TaskListResponse extends PaginatedResponse<Task> {}

export interface TaskFilters {
  status?: string | string[];
  assigned_to_id?: number;
  lead_id?: number;
  loan_id?: number;
  due_before?: string;
  due_after?: string;
  priority?: string;
}

// ============================================================================
// ACTIVITY API TYPES
// ============================================================================

export interface ActivityCreateRequest {
  type: string;
  subject?: string;
  description?: string;
  lead_id?: number;
  loan_id?: number;
  metadata?: Record<string, unknown>;
}

export interface ActivityListResponse extends PaginatedResponse<Activity> {}

// ============================================================================
// DASHBOARD API TYPES
// ============================================================================

export interface DashboardStats {
  total_leads: number;
  new_leads_today: number;
  leads_by_stage: Record<string, number>;
  total_loans: number;
  loans_closing_this_month: number;
  loans_by_stage: Record<string, number>;
  total_pipeline_value: number;
  conversion_rate: number;
  average_days_to_close: number;
}

export interface PipelineMetrics {
  total_count: number;
  total_volume: number;
  by_stage: Array<{
    stage: string;
    count: number;
    volume: number;
  }>;
  closing_soon: number;
  at_risk: number;
}

// ============================================================================
// CALENDAR API TYPES
// ============================================================================

export interface CalendarEvent {
  id: number;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  description?: string;
  location?: string;
  attendees?: string[];
  lead_id?: number;
  loan_id?: number;
  user_id: number;
  event_type: string;
  created_at: string;
}

export interface CalendarEventCreateRequest {
  title: string;
  start: string;
  end: string;
  all_day?: boolean;
  description?: string;
  location?: string;
  attendees?: string[];
  lead_id?: number;
  loan_id?: number;
  event_type?: string;
}

// ============================================================================
// FILE UPLOAD API TYPES
// ============================================================================

export interface FileUploadResponse {
  id: number;
  filename: string;
  original_filename: string;
  content_type: string;
  size: number;
  url: string;
  created_at: string;
}

export interface DocumentUploadRequest {
  file: File;
  document_type: string;
  lead_id?: number;
  loan_id?: number;
  description?: string;
}

// ============================================================================
// WEBHOOK & INTEGRATION API TYPES
// ============================================================================

export interface WebhookPayload {
  event: string;
  data: Record<string, unknown>;
  timestamp: string;
  organization_id: number;
}

export interface IntegrationConfig {
  id: number;
  integration_type: string;
  is_active: boolean;
  settings: Record<string, unknown>;
  last_sync_at: string | null;
  created_at: string;
}
