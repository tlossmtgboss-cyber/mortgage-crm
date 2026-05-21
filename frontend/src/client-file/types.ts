// ─────────────────────────────────────────────────────────────────────────
// Types — Perennia Client File LO surface
//
// These mirror the backend response shapes for /api/v1/clients/* and
// /v1/cadence/* endpoints. They're the contract between API and UI.
// Keep in sync with the Pydantic schemas.
// ─────────────────────────────────────────────────────────────────────────

export type LifecycleStage =
  | "new_lead"
  | "contacted"
  | "engaged"
  | "prospect"
  | "pre_app"
  | "pre_approved"
  | "shopping"
  | "under_contract"
  | "active_borrower"
  | "in_processing"
  | "in_underwriting"
  | "clear_to_close"
  | "closed_active"
  | "closed_past_client"
  | "post_close"
  | "dead";

export type LoanProgram =
  | "conventional"
  | "fha"
  | "va"
  | "usda"
  | "jumbo"
  | "non_qm"
  | "heloc";

export type LoanPurpose = "purchase" | "refinance" | "cash_out_refi" | "heloc";

export type MessageChannel =
  | "email"
  | "sms"
  | "call"
  | "voice_agent"
  | "portal"
  | "partner_feed"
  | "note"
  | "system";

export type MessageDirection = "inbound" | "outbound" | "internal";

export interface Address {
  street?: string;
  unit?: string;
  city?: string;
  state?: string;
  zip?: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Aggregate root
// ─────────────────────────────────────────────────────────────────────────

export interface ClientFile {
  id: string;
  org_id: string;
  // Identity
  first_name: string;
  last_name: string;
  middle_name?: string | null;
  preferred_name?: string | null;
  primary_email?: string | null;
  secondary_email?: string | null;
  primary_phone?: string | null;
  secondary_phone?: string | null;
  date_of_birth?: string | null; // ISO date
  ssn_last_4?: string | null; // last 4 only — never full SSN
  mailing_address?: Address | null;
  property_address?: Address | null;
  language_pref: string;
  preferred_channel?: MessageChannel | null;
  preferred_contact_window?: string | null;
  sticky_note?: string | null;
  // Lifecycle
  lifecycle_stage: LifecycleStage;
  source?: string | null;
  assigned_loan_officer_id?: string | null;
  assigned_loan_officer_name?: string | null;
  assigned_loan_assistant_id?: string | null;
  assigned_processor_id?: string | null;
  // Rollups
  last_contact_at?: string | null;
  last_inbound_at?: string | null;
  last_outbound_at?: string | null;
  unread_thread_count: number;
  open_doc_request_count: number;
  // Flexible
  tags: string[];
  custom_fields: Record<string, unknown>;
  // Loan rollups
  active_loan_id?: string | null;
  active_loan_program?: LoanProgram | null;
  active_loan_purpose?: LoanPurpose | null;
  active_loan_amount?: number | null;
  active_loan_fico?: number | null;
  active_loan_lock_expires_at?: string | null;
  active_loan_projected_close_date?: string | null;
  active_loan_current_milestone?: string | null;
  active_loan_stage?: string | null;
  active_loan_type?: string | null;
  active_loan_term?: number | null;
  active_loan_purchase_price?: number | null;
  active_loan_interest_rate?: number | null;
  lead_id?: number | null;
  // Audit
  created_at: string;
  updated_at: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Activity timeline
// ─────────────────────────────────────────────────────────────────────────

export type ActivityCategory =
  | "all"
  | "notes"
  | "calls"
  | "texts"
  | "emails"
  | "activity"
  | "marketing"
  | "documents"
  | "milestones"
  | "tasks"
  | "follow_ups"
  | "starred";

export type ActivityEventKind =
  // Messages
  | "message_received_email" | "message_received_sms" | "message_received_portal"
  | "message_sent_email" | "message_sent_sms" | "message_sent_voice_agent"
  | "message_sent_portal"
  // Calls
  | "call_inbound" | "call_outbound" | "call_missed" | "call_voicemail"
  // Notes
  | "note_added"
  // Documents
  | "document_requested" | "document_uploaded" | "document_approved"
  | "document_rejected" | "document_stale_reopened"
  // Milestones
  | "milestone_reached" | "milestone_at_risk" | "milestone_predicted_slip"
  // Lifecycle
  | "lifecycle_stage_changed"
  // Tasks
  | "task_created" | "task_completed"
  | "appointment_booked"
  // Action plans (LO-defined)
  | "action_plan_started" | "action_plan_step_executed"
  | "action_plan_paused" | "action_plan_completed"
  // Cadence (autonomous)
  | "cadence_sequence_started"
  | "cadence_attempt_sent"
  | "cadence_attempt_blocked"
  | "cadence_sequence_paused"
  | "cadence_sequence_won"
  | "cadence_sequence_lost"
  | "cadence_handoff_to_lo"
  // Insights
  | "insight_refreshed" | "insight_risk_alert"
  // Tags / collaborators
  | "tag_added" | "tag_removed"
  | "collaborator_added" | "collaborator_removed"
  // Web
  | "property_viewed" | "portal_logged_in" | "email_opened" | "email_link_clicked";

export interface TimelineEvent {
  id: string;
  org_id: string;
  client_file_id: string;
  kind: ActivityEventKind;
  category: ActivityCategory;
  occurred_at: string;
  headline: string;
  body?: string | null;
  // Actor — exactly one of user, agent, or system
  actor_user_id?: string | null;
  actor_user_name?: string | null;
  actor_agent_slug?: string | null; // "cadence" | "aria" | "avery" | "insight" | "ops_manager" | "document"
  actor_agent_skill?: string | null; // e.g. "gentle_nudge"
  actor_agent_skill_version?: string | null; // e.g. "v1.2"
  actor_is_system: boolean;
  // Cross-references
  related_message_id?: string | null;
  related_thread_id?: string | null;
  related_document_request_id?: string | null;
  related_task_id?: string | null;
  related_cadence_sequence_id?: string | null;
  // Compliance / metadata
  compliance_review_passed?: boolean | null;
  metadata: Record<string, unknown>;
  is_starred: boolean;
  ai_generated: boolean;
}

// ─────────────────────────────────────────────────────────────────────────
// Insights
// ─────────────────────────────────────────────────────────────────────────

export type EngagementTrajectory = "rising" | "flat" | "falling";

export type NextBestAction =
  | "call_now"
  | "send_followup_sms"
  | "send_followup_email"
  | "request_document"
  | "schedule_call"
  | "send_rate_update"
  | "request_referral"
  | "check_in_post_close"
  | "escalate_to_manager"
  | "no_action_needed"
  | "lo_handoff";

export interface ClientInsight {
  id: string;
  client_file_id: string;
  engagement_score: number; // 0-100
  engagement_trajectory: EngagementTrajectory;
  sentiment_avg_30d: number; // -1..1
  inferred_preferred_channel?: MessageChannel | null;
  inferred_preferred_time_of_day?: string | null;
  typical_response_minutes?: number | null;
  next_best_action: NextBestAction;
  next_best_action_reason: string;
  next_best_action_confidence: number; // 0..1
  risk_signals: Record<string, boolean>;
  computed_at: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "normal" | "high" | "urgent";

export interface Task {
  id: string;
  client_file_id: string;
  title: string;
  body?: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_at?: string | null;
  completed_at?: string | null;
  assigned_to_user_id?: string | null;
  assigned_to_user_name?: string | null;
  created_by_user_id?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Documents
// ─────────────────────────────────────────────────────────────────────────

export type DocumentSetType =
  | "income" | "assets" | "credit" | "identity" | "property"
  | "insurance" | "disclosures" | "conditions" | "closing"
  | "post_close" | "other";

export type DocumentRequestStatus =
  | "pending" | "submitted" | "under_review"
  | "rejected" | "fulfilled" | "waived" | "expired";

export type DocumentRequestPriority = "low" | "normal" | "high" | "blocking";

export interface DocumentSet {
  id: string;
  set_type: DocumentSetType;
  title: string;
  open_count: number;
  fulfilled_count: number;
  rejected_count: number;
  requests: DocumentRequest[];
}

export interface DocumentRequest {
  id: string;
  client_file_id: string;
  document_set_id: string;
  doc_type: string;
  title: string;
  description?: string | null;
  status: DocumentRequestStatus;
  priority: DocumentRequestPriority;
  due_at?: string | null;
  expires_after_days?: number | null;
  fulfilled_at?: string | null;
  rejection_reason?: string | null;
  is_stale?: boolean;
}

// Detailed document types for full document management

export type SmartDocStatus =
  | "UPLOADED" | "SCANNING" | "PROCESSING" | "PENDING_REVIEW"
  | "NEEDS_REVIEW" | "APPROVED" | "REJECTED" | "EXPIRED"
  | "DELETED" | "SUPERSEDED" | "UPLOAD_FAILED";

export type DocDecision = "ACCEPT" | "REJECT" | "NEEDS_REVIEW";

export type RejectionCategory =
  | "SCREENSHOT" | "EXPIRED" | "POOR_QUALITY" | "INCOMPLETE" | "WRONG_TYPE" | "OTHER";

export interface SmartDocRequest {
  id: number;
  loan_id: number;
  doc_type: string;
  title: string;
  description?: string | null;
  instructions?: string | null;
  status: string;
  priority: string;
  due_date?: string | null;
  sla_due_at?: string | null;
  freshness_days?: number | null;
  fulfilled_at?: string | null;
  created_at?: string | null;
}

export interface SmartDocument {
  id: number;
  request_id?: number | null;
  loan_id?: number | null;
  file_name: string;
  original_filename?: string | null;
  mime_type: string;
  file_size: number;
  page_count?: number | null;
  doc_type?: string | null;
  detected_doc_type?: string | null;
  display_name?: string | null;
  status: SmartDocStatus;
  decision?: DocDecision | null;
  decision_reasons?: string[] | null;
  rejection_reason?: string | null;
  rejection_category?: RejectionCategory | null;
  fix_instructions?: string | null;
  detected_is_screenshot?: boolean;
  screenshot_confidence?: number | null;
  is_expired?: boolean;
  doc_date?: string | null;
  doc_expires_at?: string | null;
  extracted_names?: string[] | null;
  extracted_employer?: string | null;
  extracted_amount?: number | null;
  extraction_confidence?: number | null;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  uploaded_at?: string | null;
  created_at?: string | null;
}

export interface DocumentsTabData {
  requests: SmartDocRequest[];
  documents: SmartDocument[];
}

// ─────────────────────────────────────────────────────────────────────────
// Cadence (autonomous follow-up)
// ─────────────────────────────────────────────────────────────────────────

export type CadenceSequenceStatus =
  | "active" | "paused" | "won" | "lost" | "expired" | "cancelled";

export type CadenceArm = "tight" | "standard" | "patient" | "voice_first";

export interface FollowupSequence {
  id: string;
  client_file_id: string;
  loan_officer_id: string;
  goal: string;
  cohort: string;
  status: CadenceSequenceStatus;
  selected_arm: CadenceArm;
  attempts_made: number;
  max_attempts: number;
  next_check_at?: string | null;
  expires_at: string;
  started_at: string;
  ended_at?: string | null;
  last_skill_used?: string | null;
  stop_reason?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Relationships
// ─────────────────────────────────────────────────────────────────────────

export type RelationshipType =
  | "spouse" | "co_borrower" | "buyers_agent" | "listing_agent"
  | "settlement_agent" | "attorney" | "gift_donor" | "power_of_attorney"
  | "referrer" | "family_decision_maker" | "past_client_referrer"
  | "employer" | "other";

export interface Relationship {
  id: string;
  relationship_type: RelationshipType;
  display_name: string;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  is_decision_maker: boolean;
  notify_on_milestone: boolean;
  consent_to_share_progress: boolean;
  // Set if linked to another ClientFile (e.g. spouse who's also a borrower)
  linked_client_file_id?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Action Plans (LO-defined deterministic sequences — distinct from Cadence)
// ─────────────────────────────────────────────────────────────────────────

export type ActionPlanRunStatus =
  | "active" | "paused" | "completed" | "cancelled" | "failed";

export interface ActionPlanRun {
  id: string;
  client_file_id: string;
  action_plan_id: string;
  action_plan_name: string;
  status: ActionPlanRunStatus;
  current_step_index: number;
  total_steps: number;
  next_step_at?: string | null;
  pause_reason?: string | null;
  started_at: string;
  ended_at?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Composer / send
// ─────────────────────────────────────────────────────────────────────────

export type ComposerChannel = "email" | "sms" | "note" | "voice_brief";

export interface ComposeMessageRequest {
  client_file_id: string;
  channel: ComposerChannel;
  body: string;
  subject?: string;
  also_start_followup?: boolean;
  followup_goal?: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Team chat — per-client-file internal coordination
// ─────────────────────────────────────────────────────────────────────────

export type TeamChatReactionEmoji = "thumbs_up" | "check" | "fire" | "question";

export interface TeamChatMember {
  user_id: string;
  display_name: string;
  initials: string;
  role: "loan_officer" | "loan_assistant" | "processor" | "underwriter" | "manager" | "compliance" | "admin";
  is_online: boolean;
  last_seen_at?: string | null;
}

export interface TeamChatAttachment {
  kind: "document_upload";
  document_upload_id: string;
  filename: string;
  size_bytes?: number;
}

// System bot — agent or system event auto-posted to the channel
export interface TeamChatSystemAuthor {
  kind: "system";
  agent_slug: "cadence" | "aria" | "avery" | "insight" | "ops_manager" | "document" | "milestone" | "lifecycle";
  display_name: string;
  // Optional: link back to the source event/object for click-through
  source_event_kind?: string;
  source_object_id?: string;
  source_object_label?: string;
}

export interface TeamChatHumanAuthor {
  kind: "human";
  user_id: string;
  display_name: string;
  initials: string;
  role: TeamChatMember["role"];
}

export type TeamChatAuthor = TeamChatHumanAuthor | TeamChatSystemAuthor;

export interface TeamChatReaction {
  emoji: TeamChatReactionEmoji;
  user_ids: string[]; // who reacted
  count: number;
  current_user_reacted: boolean;
}

export interface TeamChatMessage {
  id: string;
  channel_id: string;
  client_file_id: string;
  author: TeamChatAuthor;
  body: string;
  mentioned_user_ids: string[];
  attachments: TeamChatAttachment[];
  reactions: TeamChatReaction[];
  is_pinned: boolean;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
}

export interface TeamChatReadCursor {
  channel_id: string;
  user_id: string;
  last_read_message_id: string;
  last_read_at: string;
}
