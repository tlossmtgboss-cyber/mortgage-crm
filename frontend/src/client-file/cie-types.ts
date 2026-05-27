// CIE — Call Intelligence Engine type definitions

export interface ScoreDetail {
  name: string;
  score: number;
  evidence: string;
}

export interface ComplianceFlag {
  type: string;
  severity: "pass" | "info" | "warning" | "high";
  message: string;
  state?: string;
  keywords?: string[];
  terms?: string[];
}

export interface CoachingSuggestion {
  area: string;
  suggestion: string;
  example?: string;
}

export interface CIEObjection {
  objection: string;
  lo_response: string;
  effectiveness: "strong" | "adequate" | "weak";
}

export interface GeneratedTask {
  title: string;
  owner: "lo" | "borrower";
  priority: "high" | "medium" | "low";
  due_days: number;
}

export interface DraftMessage {
  channel: "sms" | "email";
  recipient: string;
  body: string;
}

export interface Opportunity {
  label: string;
  description: string;
  priority: "high" | "medium" | "low";
}

export interface Risk {
  label: string;
  description: string;
  severity: "high" | "medium" | "low";
}

export interface CIEReport {
  id: string;
  call_record_id: string;

  cis_composite: number | null;
  engagement_score: number | null;
  information_quality_score: number | null;
  objection_handling_score: number | null;
  compliance_score: number | null;
  rapport_score: number | null;
  closing_effectiveness_score: number | null;

  primary_intent: string | null;
  intent_confidence: number | null;

  conversion_probability: number | null;
  conversion_ci_low: number | null;
  conversion_ci_high: number | null;

  summary: string | null;
  summary_bullets: string[] | null;
  opportunities: Opportunity[] | null;
  risks: Risk[] | null;
  objections: CIEObjection[] | null;
  compliance_flags: ComplianceFlag[] | null;
  coaching_suggestions: CoachingSuggestion[] | null;
  generated_tasks: GeneratedTask[] | null;
  draft_messages: DraftMessage[] | null;

  llm_model_used: string | null;
  pipeline_version: string | null;
  processing_time_ms: number | null;

  created_at: string;
  updated_at: string;
}

export interface CallRecordBrief {
  id: string;
  external_call_id: string;
  provider: string;
  direction: string;
  started_at: string | null;
  duration_seconds: number | null;
  processing_status: string;
  created_at: string;
}

export interface ReportListItem {
  call: CallRecordBrief;
  report: CIEReport | null;
}

export interface ReportListResponse {
  items: ReportListItem[];
  total: number;
}

export interface CIEStats {
  total_calls: number;
  analyzed: number;
  pending: number;
  failed: number;
  avg_cis: number | null;
  avg_conversion: number | null;
}
