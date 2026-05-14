/**
 * Shared types for the LoanDetail page components.
 */

export interface Borrower {
  id: number;
  name: string;
  type: 'primary' | 'co-borrower' | 'additional';
  data: {
    name?: string;
    email?: string;
    phone?: string;
    borrower_name?: string;
    borrower_first_name?: string;
    borrower_last_name?: string;
    [key: string]: any;
  };
}

export interface CircleContact {
  id: number;
  loanId: number | null;
  name: string;
  email: string;
  phone: string;
  type: string;
  notes: string;
}

export interface CircleContactType {
  value: string;
  icon: string;
}

export interface CircleForm {
  name: string;
  email: string;
  phone: string;
  type: string;
  notes: string;
  editId?: number;
  loanId?: number | null;
}

export interface Condition {
  id: number;
  name: string;
  description?: string;
  category?: string;
  priority?: string;
  status: string;
  due_date?: string;
  is_new?: boolean;
}

export interface NewCondition {
  name: string;
  description: string;
  category: string;
  priority: string;
  due_date: string;
}

export interface TeamMember {
  id: number;
  name: string;
  role: string;
  email?: string;
  phone?: string;
  company?: string;
  license_number?: string;
  notes?: string;
  is_employee?: boolean;
  is_new?: boolean;
  referral_partner_id?: number;
}

export interface TeamMemberForm {
  name: string;
  role: string;
  email: string;
  phone: string;
  company: string;
  license_number: string;
  notes: string;
  is_employee: boolean;
}

export interface CustomField {
  key: string;
  label: string;
}

export interface SalesforceStatus {
  salesforce_id?: string;
  is_linked?: boolean;
  last_synced_at?: string;
  sync_status?: string;
  needs_sync?: boolean;
}

export interface LoanData {
  id: number;
  borrower_name?: string;
  borrower?: string;
  borrower_email?: string;
  borrower_phone?: string;
  borrower_first_name?: string;
  borrower_last_name?: string;
  coborrower_name?: string;
  co_borrower_email?: string;
  co_borrower_phone?: string;
  loan_number?: string;
  loan_amount?: number;
  amount?: number;
  interest_rate?: number;
  loan_term?: number;
  term?: number;
  loan_type?: string;
  program?: string;
  loan_purpose?: string;
  stage?: string;
  property_address?: string;
  address?: string;
  lead_id?: number;
  borrower_id?: number;
  salesforce_id?: string;
  salesforce_last_synced_at?: string;
  closing_date?: string;
  loan_officer_id?: number;
  coborrower_email?: string;
  [key: string]: any;
}

export interface SearchResult {
  id: number;
  name?: string;
  borrower_name?: string;
  email?: string;
  borrower_email?: string;
  phone?: string;
  borrower_phone?: string;
  company?: string;
  type?: string;
}

export type ActiveTab =
  | 'loan-details'
  | 'personal'
  | 'loan'
  | 'tasks'
  | 'conversation'
  | 'circle'
  | 'smart-docs'
  | 'credit'
  | 'income'
  | 'documents'
  | 'important-dates'
  | 'team'
  | 'ai-activity'
  | 'employment'
  | 'email'
  | 'marketing';

export type ArchiveSubTab = 'notes' | 'email' | 'sms' | 'calls';
export type PropertySubTab = 'property' | 'insurance' | 'legal';
export type PersonalSubTab = 'info' | 'employment' | 'assets';
