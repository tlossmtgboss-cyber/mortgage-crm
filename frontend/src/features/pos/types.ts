// POS feature TypeScript types — mirror backend Pydantic schemas exactly.

export type SectionKey =
  | 'personal'
  | 'residence'
  | 'employment'
  | 'assets'
  | 'liabilities'
  | 'reo'
  | 'loan'
  | 'declarations'
  | 'review';

export const SECTION_ORDER: SectionKey[] = [
  'personal',
  'residence',
  'employment',
  'assets',
  'liabilities',
  'reo',
  'loan',
  'declarations',
  'review',
];

export const SECTION_LABELS: Record<SectionKey, string> = {
  personal: 'Personal Information',
  residence: 'Address & Contact',
  employment: 'Employment & Income',
  assets: 'Assets',
  liabilities: 'Liabilities',
  reo: 'Real Estate Owned',
  loan: 'Loan & Property',
  declarations: 'Declarations',
  review: 'Review & eSign',
};

export const SECTION_CAPTIONS: Record<SectionKey, string> = {
  personal: 'Legal name, date of birth, ID',
  residence: 'Where you live and how to reach you',
  employment: 'Current job, prior history, other income',
  assets: 'Bank, retirement, gifts and credits',
  liabilities: 'Credit cards, loans, monthly obligations',
  reo: 'Properties you currently own',
  loan: 'Subject property and loan details',
  declarations: 'Disclosure questions and HMDA',
  review: 'Final review and submission',
};

export type ApplicationStatus = 'draft' | 'submitted' | 'abandoned' | 'withdrawn';

export interface ApplicationResponse {
  id: string;
  loan_id: number | null;
  status: ApplicationStatus;
  current_step: SectionKey;
  completion_pct: number;
  submitted_at: string | null;
  submitted_appointment_id: number | null;
  created_at: string;
  updated_at: string;
  sections_complete: Partial<Record<SectionKey, boolean>>;
  has_ssn: boolean;
  has_co_ssn: boolean;
  has_dob: boolean;
}

export interface SectionResponse {
  section_key: SectionKey;
  data: Record<string, unknown>;
  is_complete: boolean;
  completed_at: string | null;
  updated_at: string;
  has_ssn: boolean;
  has_co_ssn: boolean;
  has_dob: boolean;
}

export interface SectionUpdateRequest {
  data: Record<string, unknown>;
  ssn?: string;
  co_ssn?: string;
  dob?: string; // ISO date YYYY-MM-DD
  co_dob?: string;
  mark_complete?: boolean;
}

export interface ApplicationSubmitRequest {
  appointment_id: number | null;
  acknowledged_certifications: string[];
}

export interface ApplicationSubmitResponse {
  id: string;
  status: 'submitted';
  submitted_at: string;
  submitted_appointment_id: number | null;
  confirmation_number: string;
  next_steps: string[];
}

// ---------- Calendar ----------

export interface TimeSlot {
  start: string; // ISO datetime
  end: string;
  is_available: boolean;
  is_recommended: boolean;
}

export interface AvailableSlotsResponse {
  application_id: string;
  loan_officer_user_id: number;
  loan_officer_name: string;
  loan_officer_nmls: string | null;
  timezone: string;
  duration_minutes: number;
  slots_by_date: Record<string, TimeSlot[]>;
  recommended_slot: TimeSlot | null;
}

export interface AssignedLOResponse {
  user_id: number;
  name: string;
  nmls: string | null;
  title: string | null;
  avatar_url: string | null;
  booking_link_slug: string | null;
}

export interface SlotHoldResponse {
  hold_id: number;
  expires_at: string;
  slot_start: string;
  slot_end: string;
}

export type MeetingType = 'checkin' | 'application_review' | 'full_consultation';

export interface BookingRequest {
  application_id: string;
  hold_id?: number | null;
  meeting_type: MeetingType;
  slot_start: string;
  slot_end: string;
  timezone: string;
  notes?: string | null;
}

export interface BookingResponse {
  appointment_id: number;
  application_id: string;
  loan_id: number | null;
  loan_officer_user_id: number;
  loan_officer_name: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  meeting_type: MeetingType;
  video_link: string | null;
  ics_link: string | null;
  confirmation_url: string;
  email_sent: boolean;
  calendar_event_created: boolean;
}

// ---------- AI Q&A ----------

export type SourceType = 'loan_file' | 'guideline' | 'perennia_doc';

export interface Source {
  type: SourceType;
  label: string;
  anchor: string | null;
}

export type Confidence = 'high' | 'medium' | 'low' | 'escalate';

export interface AskRequest {
  application_id: string;
  message: string;
  context_message_ids?: number[] | null;
  current_step?: string | null;
}

export interface AskResponse {
  message_id: number;
  application_id: string;
  role: 'aria';
  content: string;
  sources: Source[];
  follow_ups: string[];
  latency_ms: number;
  confidence: Confidence;
  escalation_recommended: boolean;
  escalation_reason: string | null;
  created_at: string;
}

export interface QAMessageResponse {
  id: number;
  role: 'borrower' | 'aria';
  content: string;
  sources: Source[] | null;
  follow_ups: string[] | null;
  confidence: string | null;
  created_at: string;
}

export interface QAHistoryResponse {
  application_id: string;
  messages: QAMessageResponse[];
  total: number;
}
