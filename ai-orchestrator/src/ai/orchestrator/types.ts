export type TaskCategory =
  | "MORTGAGE_GUIDELINE"
  | "LOAN_STATUS"
  | "CLIENT_FOLLOW_UP"
  | "APPOINTMENT_SCHEDULING"
  | "LOAN_PRICING"
  | "CRM_NAVIGATION"
  | "PORTFOLIO_ANALYSIS"
  | "OPERATIONS"
  | "COMPLIANCE"
  | "GENERAL_KNOWLEDGE";

export interface UserMessage {
  userId: string;
  sessionId: string;
  text: string;
  channel: "web" | "sms" | "phone" | "email" | "internal";
  metadata?: {
    conversationHistory?: Array<{ role: "user" | "assistant"; text: string }>;
    activeLeadId?: string;
    activeLoanId?: string;
    [key: string]: any;
  };
}

export type ContextType =
  | "LEAD"
  | "LOAN"
  | "PIPELINE"
  | "EMAIL_THREAD"
  | "SMS_THREAD"
  | "CALENDAR"
  | "NOTES"
  | "RATE_SHEET"
  | "KNOWLEDGE_BASE";

export interface RetrievedContext {
  lead?: any;
  loan?: any;
  pipeline?: any;
  emails?: any[];
  sms?: any[];
  calendar?: any[];
  notes?: any[];
  rateSheet?: any;
  kbArticles?: any[];
}

export interface GroundingSnapshot {
  participantSummary: {
    borrowerName?: string;
    coBorrowerName?: string;
    agents?: string[];
    emails?: string[];
    phones?: string[];
  };
  loanSnapshot?: {
    loanId?: string;
    product?: string;
    purpose?: string;
    occupancy?: string;
    rate?: number | null;
    lockStatus?: string;
    loanAmount?: number | null;
    purchasePrice?: number | null;
    ltv?: number | null;
    stage?: string;
    importantDates?: {
      appDate?: string;
      lockDate?: string;
      closingDate?: string;
    };
    keyConditions?: string[];
  };
  timeline: Array<{
    type: "NOTE" | "EMAIL" | "SMS" | "TASK" | "STATUS";
    date: string;
    summary: string;
  }>;
  openTasks: Array<{
    taskId?: string;
    title: string;
    dueDate?: string;
    status: "OPEN" | "IN_PROGRESS" | "DONE";
  }>;
  kbSummary: string[];
  rawIds: {
    leadId?: string;
    loanId?: string;
  };
}

export interface TaskRoutingResult {
  category: TaskCategory;
  requiresContext: boolean;
  requiredContextTypes: ContextType[];
}

export interface BrainInput {
  userMessage: UserMessage;
  routing: TaskRoutingResult;
  context: RetrievedContext;
  grounding: GroundingSnapshot;
}

export interface PlannedAction {
  type: ActionType;
  payload: Record<string, any>;
  requiresApproval: boolean;
}

export type ActionType =
  | "CREATE_TASK"
  | "ADD_NOTE"
  | "UPDATE_LOAN_STATUS"
  | "SCHEDULE_APPOINTMENT"
  | "SEND_EMAIL_DRAFT"
  | "SEND_SMS_DRAFT";

export interface BrainStructuredOutput {
  answer: string;
  assumptions: string[];
  actions: PlannedAction[];
  warnings: string[];
  reasoningSummary?: string;
  usedContextKeys?: string[];
}

export interface ConfidenceEvaluation {
  confidence: number;
  groundingScore: number;
  completenessScore: number;
  riskScore: number;
  issues: string[];
  riskLevel: "LOW" | "MEDIUM" | "HIGH";
}

export interface AssistantFinalAnswer {
  answer: string;
  confidence: number;
  escalationRequired: boolean;
  escalationReason?: string;
  actionsExecuted?: PlannedAction[];
  meta?: Record<string, any>;
}
