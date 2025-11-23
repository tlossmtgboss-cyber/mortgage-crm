import { TaskCategory, ActionType } from "../orchestrator/types";

interface CategoryConfig {
  minConfidenceThreshold: number;
  allowedAutoActions: ActionType[];
  requiresEscalationReview: boolean;
}

export const CATEGORY_CONFIG: Record<TaskCategory, CategoryConfig> = {
  MORTGAGE_GUIDELINE: {
    minConfidenceThreshold: 0.75,
    allowedAutoActions: ["ADD_NOTE"],
    requiresEscalationReview: true
  },
  LOAN_STATUS: {
    minConfidenceThreshold: 0.60,
    allowedAutoActions: ["ADD_NOTE", "CREATE_TASK"],
    requiresEscalationReview: false
  },
  CLIENT_FOLLOW_UP: {
    minConfidenceThreshold: 0.65,
    allowedAutoActions: ["CREATE_TASK", "ADD_NOTE", "SEND_EMAIL_DRAFT", "SEND_SMS_DRAFT"],
    requiresEscalationReview: false
  },
  APPOINTMENT_SCHEDULING: {
    minConfidenceThreshold: 0.70,
    allowedAutoActions: ["SCHEDULE_APPOINTMENT", "ADD_NOTE"],
    requiresEscalationReview: false
  },
  LOAN_PRICING: {
    minConfidenceThreshold: 0.80,
    allowedAutoActions: ["ADD_NOTE"],
    requiresEscalationReview: true
  },
  CRM_NAVIGATION: {
    minConfidenceThreshold: 0.50,
    allowedAutoActions: [],
    requiresEscalationReview: false
  },
  PORTFOLIO_ANALYSIS: {
    minConfidenceThreshold: 0.70,
    allowedAutoActions: ["ADD_NOTE", "CREATE_TASK"],
    requiresEscalationReview: false
  },
  OPERATIONS: {
    minConfidenceThreshold: 0.65,
    allowedAutoActions: ["CREATE_TASK", "ADD_NOTE", "UPDATE_LOAN_STATUS"],
    requiresEscalationReview: false
  },
  COMPLIANCE: {
    minConfidenceThreshold: 0.85,
    allowedAutoActions: ["ADD_NOTE"],
    requiresEscalationReview: true
  },
  GENERAL_KNOWLEDGE: {
    minConfidenceThreshold: 0.50,
    allowedAutoActions: [],
    requiresEscalationReview: false
  }
};

export function getCategoryConfig(category: TaskCategory): CategoryConfig {
  return CATEGORY_CONFIG[category];
}

export function shouldEscalate(
  category: TaskCategory,
  confidence: number,
  riskLevel: "LOW" | "MEDIUM" | "HIGH"
): boolean {
  const config = CATEGORY_CONFIG[category];

  if (confidence < config.minConfidenceThreshold) return true;
  if (riskLevel === "HIGH") return true;
  if (config.requiresEscalationReview && riskLevel === "MEDIUM") return true;

  return false;
}

export function canAutoExecuteAction(
  category: TaskCategory,
  actionType: ActionType,
  requiresApproval: boolean
): boolean {
  if (requiresApproval) return false;

  const config = CATEGORY_CONFIG[category];
  return config.allowedAutoActions.includes(actionType);
}
