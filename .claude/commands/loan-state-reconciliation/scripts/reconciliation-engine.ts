// ─────────────────────────────────────────────────────────────────────────────
// Loan State Reconciliation Engine
// Reference implementation for Perennia AI Salesforce sync pipeline
// ─────────────────────────────────────────────────────────────────────────────

// ─── Types ──────────────────────────────────────────────────────────────────

type Pipeline = 'leads' | 'active_loans' | 'mum';
type ReconciliationAction = 'stay' | 'transition' | 'flag_for_review' | 'archive' | 'reactivate';

interface AuditEntry {
  event: string;
  from_pipeline?: Pipeline;
  to_pipeline?: Pipeline;
  from_milestone?: string;
  to_milestone?: string;
  trigger: string;
  trigger_type: 'stage_change' | 'date_field' | 'manual' | 'reactivation';
  salesforce_opportunity_id: string;
  crm_record_id: string;
  user_id: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

interface ValidationError {
  field: string;
  message: string;
  severity: 'block' | 'warn';
}

interface ReconciliationResult {
  action: ReconciliationAction;
  from_pipeline?: Pipeline;
  to_pipeline?: Pipeline;
  new_milestone?: string;
  new_substatus?: string | null;
  validation_errors: ValidationError[];
  warnings: string[];
  audit_entry: AuditEntry;
  workflows_to_fire: string[];
  sla_action?: 'start' | 'stop' | 'pause' | 'restart';
}

interface CRMRecord {
  id: string;
  pipeline: Pipeline;
  milestone: string;
  substatus: string | null;
  borrower_name: string | null;
  borrower_email: string | null;
  loan_amount: number | null;
  loan_number: string | null;
  final_loan_amount: number | null;
  interest_rate: number | null;
  funding_date: string | null;
  property_address: string | null;
  salesforce_opportunity_id: string;
  user_id: string;
  last_transition_at: string | null;
}

interface SalesforceRecord {
  Id: string;
  StageName: string;
  Contract_Received_Date__c?: string | null;
  Submitted_To_Processing_Date__c?: string | null;
  Processing_Start_Date__c?: string | null;
  Application_Submission_Date__c?: string | null;
  App_Submitted_Date__c?: string | null;
  Funding_Date__c?: string | null;
  Funded_Date__c?: string | null;
  Fund_Date__c?: string | null;
  Loan_Funded_Date__c?: string | null;
  [key: string]: unknown;
}

// ─── Stage Classification Maps ──────────────────────────────────────────────

const LEAD_STAGES = new Set([
  'New Lead', 'Attempted Contact', 'Contacted', 'Initial Consultation',
  'Pre-Qualified', 'Pre-Approved', 'Application Complete',
  'Qualification', 'Needs Analysis', 'Prospecting',
]);

const ACTIVE_LOAN_ENTRY_STAGES = new Set([
  'Contract Received', 'Submitted to Processing', 'In Processing',
  'Application Submitted', 'Document Collection',
  'Submitted to Underwriting', 'In Underwriting',
]);

const ACTIVE_LOAN_STAGES = new Set([
  'Contract Received', 'Submitted to Processing', 'In Processing',
  'Application Submitted', 'Document Collection', 'Documents Requested',
  'Documents Received', 'Appraisal Ordered', 'Appraisal Received',
  'Insurance Ordered', 'Insurance Received', 'Title Ordered', 'Title Received',
  'Submitted to Underwriting', 'In Underwriting', 'Underwriting Decision',
  'Approved', 'Conditional Approval', 'Conditions Cleared',
  'Clear to Close', 'Closing Docs Out', 'Closing Scheduled', 'Closing Date',
]);

const MUM_ENTRY_STAGES = new Set([
  'Funded', 'Loan Funded', 'Closed', 'Closed Won', 'Post-Closing',
]);

const SUSPENDED_STAGES = new Set(['Suspended', 'On Hold', 'Paused']);
const WITHDRAWN_STAGES = new Set(['Withdrawn', 'Cancelled', 'Lost', 'Closed Lost']);
const DENIED_STAGES = new Set(['Denied', 'Declined', 'Adverse Action']);

// ─── Milestone Mapping ──────────────────────────────────────────────────────

const STAGE_TO_MILESTONE: Record<string, { milestone: string; substatus?: string }> = {
  'New Lead':                  { milestone: 'NEW_LEAD' },
  'Attempted Contact':         { milestone: 'ATTEMPTED_CONTACT' },
  'Contacted':                 { milestone: 'CONTACTED' },
  'Initial Consultation':      { milestone: 'INITIAL_CONSULTATION' },
  'Pre-Qualified':             { milestone: 'PRE_QUALIFIED' },
  'Pre-Approved':              { milestone: 'PRE_APPROVED' },
  'Application Complete':      { milestone: 'APPLICATION_COMPLETE' },
  'Contract Received':         { milestone: 'CONTRACT_RECEIVED' },
  'Submitted to Processing':   { milestone: 'SUBMITTED_TO_PROCESSING' },
  'In Processing':             { milestone: 'LOAN_IN_PROCESSING' },
  'Application Submitted':     { milestone: 'APPLICATION_SUBMITTED' },
  'Document Collection':       { milestone: 'DOCUMENT_COLLECTION' },
  'Documents Requested':       { milestone: 'DOCUMENTS_REQUESTED' },
  'Documents Received':        { milestone: 'DOCUMENTS_RECEIVED' },
  'Appraisal Ordered':         { milestone: 'APPRAISAL_ORDERED' },
  'Appraisal Received':        { milestone: 'APPRAISAL_RECEIVED' },
  'Insurance Ordered':         { milestone: 'INSURANCE_ORDERED' },
  'Insurance Received':        { milestone: 'INSURANCE_RECEIVED' },
  'Title Ordered':             { milestone: 'TITLE_ORDERED' },
  'Title Received':            { milestone: 'TITLE_RECEIVED' },
  'Submitted to Underwriting': { milestone: 'LOAN_SUBMITTED_TO_UW' },
  'In Underwriting':           { milestone: 'LOAN_IN_UW' },
  'Underwriting Decision':     { milestone: 'UW_DECISION' },
  'Approved':                  { milestone: 'LOAN_APPROVED' },
  'Conditional Approval':      { milestone: 'LOAN_APPROVED', substatus: 'conditional' },
  'Conditions Cleared':        { milestone: 'CONDITIONS_CLEARED' },
  'Clear to Close':            { milestone: 'LOAN_CTC' },
  'Closing Docs Out':          { milestone: 'CLOSING_DOCS_OUT' },
  'Closing Scheduled':         { milestone: 'LOAN_CLOSING_SCHEDULED' },
  'Closing Date':              { milestone: 'LOAN_CLOSING_SCHEDULED' },
  'Funded':                    { milestone: 'LOAN_FUNDED' },
  'Loan Funded':               { milestone: 'LOAN_FUNDED' },
  'Closed':                    { milestone: 'LOAN_FUNDED' },
  'Closed Won':                { milestone: 'LOAN_FUNDED' },
  'Post-Closing':              { milestone: 'LOAN_FUNDED' },
};

// Milestone ordering for backward movement detection
const MILESTONE_ORDER: Record<string, number> = {
  NEW_LEAD: 0, ATTEMPTED_CONTACT: 1, CONTACTED: 2, INITIAL_CONSULTATION: 3,
  PRE_QUALIFIED: 4, PRE_APPROVED: 5, APPLICATION_COMPLETE: 6,
  CONTRACT_RECEIVED: 10, SUBMITTED_TO_PROCESSING: 11, LOAN_IN_PROCESSING: 12,
  APPLICATION_SUBMITTED: 13, DOCUMENT_COLLECTION: 14, DOCUMENTS_REQUESTED: 15,
  DOCUMENTS_RECEIVED: 16, APPRAISAL_ORDERED: 20, APPRAISAL_RECEIVED: 21,
  INSURANCE_ORDERED: 22, INSURANCE_RECEIVED: 23, TITLE_ORDERED: 24, TITLE_RECEIVED: 25,
  LOAN_SUBMITTED_TO_UW: 30, LOAN_IN_UW: 31, UW_DECISION: 32,
  LOAN_APPROVED: 40, CONDITIONS_CLEARED: 41,
  LOAN_CTC: 50, CLOSING_DOCS_OUT: 51, LOAN_CLOSING_SCHEDULED: 52,
  LOAN_FUNDED: 60,
};

// ─── Date Field Trigger Detection ───────────────────────────────────────────

function checkDateFieldTriggers(sfRecord: SalesforceRecord): {
  triggersActiveTransition: boolean;
  triggersMumTransition: boolean;
  triggerField: string | null;
} {
  // Check if date fields indicate a Lead → Active transition
  const activeTransitionFields = [
    'Contract_Received_Date__c', 'Contract_Date__c',
    'Submitted_To_Processing_Date__c', 'Processing_Start_Date__c',
    'Application_Submission_Date__c', 'App_Submitted_Date__c',
  ];

  for (const field of activeTransitionFields) {
    if (sfRecord[field]) {
      return { triggersActiveTransition: true, triggersMumTransition: false, triggerField: field };
    }
  }

  // Check if date fields indicate an Active → MUM transition
  const mumTransitionFields = [
    'Funding_Date__c', 'Funded_Date__c', 'Fund_Date__c', 'Loan_Funded_Date__c',
  ];

  for (const field of mumTransitionFields) {
    if (sfRecord[field]) {
      return { triggersActiveTransition: false, triggersMumTransition: true, triggerField: field };
    }
  }

  return { triggersActiveTransition: false, triggersMumTransition: false, triggerField: null };
}

// ─── Validation ─────────────────────────────────────────────────────────────

function validateLeadToActive(record: CRMRecord): ValidationError[] {
  const errors: ValidationError[] = [];

  if (!record.borrower_name) {
    errors.push({ field: 'borrower_name', message: 'Borrower name is required', severity: 'block' });
  }
  if (!record.borrower_email) {
    errors.push({ field: 'borrower_email', message: 'Borrower email is required', severity: 'block' });
  }
  if (!record.loan_amount || record.loan_amount <= 0) {
    errors.push({ field: 'loan_amount', message: 'Loan amount must be populated', severity: 'block' });
  }

  return errors;
}

function validateActiveToMum(record: CRMRecord, sfRecord: SalesforceRecord): ValidationError[] {
  const errors: ValidationError[] = [];

  const fundingDate = sfRecord.Funding_Date__c || sfRecord.Funded_Date__c ||
                      sfRecord.Fund_Date__c || sfRecord.Loan_Funded_Date__c || record.funding_date;
  if (!fundingDate) {
    errors.push({ field: 'funding_date', message: 'Funding date is required', severity: 'block' });
  }
  if (!record.loan_number) {
    errors.push({ field: 'loan_number', message: 'Loan number must be assigned', severity: 'block' });
  }
  if (!record.final_loan_amount && !record.loan_amount) {
    errors.push({ field: 'final_loan_amount', message: 'Final loan amount must be populated', severity: 'warn' });
  }
  if (!record.interest_rate) {
    errors.push({ field: 'interest_rate', message: 'Interest rate must be populated', severity: 'warn' });
  }

  return errors;
}

// ─── Core Reconciliation Engine ─────────────────────────────────────────────

export function reconcileLoanState(
  currentRecord: CRMRecord,
  incomingSalesforceData: SalesforceRecord,
): ReconciliationResult {
  const sfStage = incomingSalesforceData.StageName;
  const currentPipeline = currentRecord.pipeline;
  const currentMilestone = currentRecord.milestone;
  const timestamp = new Date().toISOString();

  const baseAudit: AuditEntry = {
    event: 'reconciliation_evaluated',
    trigger: sfStage,
    trigger_type: 'stage_change',
    salesforce_opportunity_id: incomingSalesforceData.Id,
    crm_record_id: currentRecord.id,
    user_id: currentRecord.user_id,
    timestamp,
  };

  const result: ReconciliationResult = {
    action: 'stay',
    validation_errors: [],
    warnings: [],
    audit_entry: baseAudit,
    workflows_to_fire: [],
  };

  // ── Check for special statuses first ──────────────────────────────────

  if (SUSPENDED_STAGES.has(sfStage)) {
    result.action = 'stay';
    result.new_substatus = 'suspended';
    result.sla_action = 'pause';
    result.workflows_to_fire.push('create_reactivation_task');
    result.audit_entry.event = 'status_suspended';
    return result;
  }

  if (WITHDRAWN_STAGES.has(sfStage)) {
    result.action = 'archive';
    result.new_substatus = 'withdrawn';
    result.sla_action = 'stop';
    result.workflows_to_fire.push('stop_all_workflows');
    if (currentPipeline === 'leads') {
      result.workflows_to_fire.push('archive_lead');
    }
    result.audit_entry.event = 'status_withdrawn';
    return result;
  }

  if (DENIED_STAGES.has(sfStage)) {
    result.action = 'archive';
    result.new_substatus = 'denied';
    result.sla_action = 'stop';
    result.workflows_to_fire.push('stop_all_workflows', 'trigger_adverse_action_compliance', 'schedule_reengage_6mo');
    result.audit_entry.event = 'status_denied';
    return result;
  }

  // ── Check for reactivation ────────────────────────────────────────────

  const isReactivation = currentRecord.substatus &&
    ['suspended', 'withdrawn', 'denied'].includes(currentRecord.substatus) &&
    !SUSPENDED_STAGES.has(sfStage) &&
    !WITHDRAWN_STAGES.has(sfStage) &&
    !DENIED_STAGES.has(sfStage);

  if (isReactivation) {
    result.action = 'reactivate';
    result.new_substatus = null;
    result.sla_action = 'restart';
    result.audit_entry.event = 'reactivation';
    result.audit_entry.trigger_type = 'reactivation';
    result.audit_entry.metadata = { previous_substatus: currentRecord.substatus };
    result.workflows_to_fire.push('clear_substatus', 'restart_sla_timers');
    // Continue evaluation to also set the correct milestone below
  }

  // ── Resolve milestone from stage ──────────────────────────────────────

  const mapped = STAGE_TO_MILESTONE[sfStage];
  const dateTriggers = checkDateFieldTriggers(incomingSalesforceData);

  if (!mapped && !dateTriggers.triggersActiveTransition && !dateTriggers.triggersMumTransition) {
    // Unmapped stage — don't change anything, flag for review
    result.action = isReactivation ? 'reactivate' : 'flag_for_review';
    result.warnings.push(`Unmapped Salesforce stage: "${sfStage}"`);
    result.audit_entry.event = 'unmapped_stage';
    result.workflows_to_fire.push('notify_admin_unmapped_stage');
    return result;
  }

  const newMilestone = mapped?.milestone || currentMilestone;
  const newSubstatus = mapped?.substatus || (isReactivation ? null : currentRecord.substatus);

  // ── Determine if pipeline transition is needed ────────────────────────

  // Case 1: Record is in Leads, stage indicates Active Loan
  if (currentPipeline === 'leads' &&
      (ACTIVE_LOAN_ENTRY_STAGES.has(sfStage) || ACTIVE_LOAN_STAGES.has(sfStage) || dateTriggers.triggersActiveTransition)) {

    const validationErrors = validateLeadToActive(currentRecord);
    const blockingErrors = validationErrors.filter(e => e.severity === 'block');

    if (blockingErrors.length > 0) {
      result.action = 'flag_for_review';
      result.validation_errors = validationErrors;
      result.audit_entry.event = 'transition_blocked_validation';
      return result;
    }

    result.action = 'transition';
    result.from_pipeline = 'leads';
    result.to_pipeline = 'active_loans';
    result.new_milestone = newMilestone;
    result.new_substatus = newSubstatus;
    result.sla_action = 'start';
    result.validation_errors = validationErrors; // Include warnings
    result.workflows_to_fire.push(
      'mark_lead_converted', 'initialize_active_loan_workflows',
      'start_sla_timers', 'assign_processing_team'
    );
    result.audit_entry = {
      ...baseAudit,
      event: 'pipeline_transition',
      from_pipeline: 'leads',
      to_pipeline: 'active_loans',
      from_milestone: currentMilestone,
      to_milestone: newMilestone,
    };
    return result;
  }

  // Case 2: Record is in Leads, stage indicates MUM (skip Active — flag it)
  if (currentPipeline === 'leads' && (MUM_ENTRY_STAGES.has(sfStage) || dateTriggers.triggersMumTransition)) {
    result.action = 'flag_for_review';
    result.warnings.push('Lead jumped directly to Funded status — cannot skip Active Loans pipeline');
    result.audit_entry.event = 'invalid_transition_lead_to_mum';
    result.workflows_to_fire.push('notify_admin_critical');
    return result;
  }

  // Case 3: Record is in Active Loans, stage indicates MUM
  if (currentPipeline === 'active_loans' &&
      (MUM_ENTRY_STAGES.has(sfStage) || dateTriggers.triggersMumTransition)) {

    const validationErrors = validateActiveToMum(currentRecord, incomingSalesforceData);
    const blockingErrors = validationErrors.filter(e => e.severity === 'block');

    if (blockingErrors.length > 0) {
      result.action = 'flag_for_review';
      result.validation_errors = validationErrors;
      result.audit_entry.event = 'transition_blocked_validation';
      return result;
    }

    result.action = 'transition';
    result.from_pipeline = 'active_loans';
    result.to_pipeline = 'mum';
    result.new_milestone = 'LOAN_FUNDED';
    result.new_substatus = null;
    result.sla_action = 'stop';
    result.validation_errors = validationErrors; // Include warnings
    result.workflows_to_fire.push(
      'mark_active_loan_funded', 'initialize_mum_record',
      'start_post_closing_workflows', 'send_thank_you_sequence',
      'schedule_review_request', 'start_referral_nurture'
    );
    result.audit_entry = {
      ...baseAudit,
      event: 'pipeline_transition',
      from_pipeline: 'active_loans',
      to_pipeline: 'mum',
      from_milestone: currentMilestone,
      to_milestone: 'LOAN_FUNDED',
    };
    return result;
  }

  // Case 4: Record stays in current pipeline — just update milestone
  if (mapped) {
    const isBackward = (MILESTONE_ORDER[newMilestone] ?? 0) < (MILESTONE_ORDER[currentMilestone] ?? 0);

    result.action = 'stay';
    result.new_milestone = newMilestone;
    result.new_substatus = newSubstatus;
    result.sla_action = isBackward ? 'restart' : 'start';

    if (isBackward) {
      result.warnings.push(`Backward stage movement: ${currentMilestone} → ${newMilestone}`);
      result.workflows_to_fire.push('notify_lo_backward_movement');
    }

    // Skip if milestone hasn't actually changed (idempotency)
    if (newMilestone === currentMilestone && newSubstatus === currentRecord.substatus && !isReactivation) {
      result.action = 'stay';
      result.sla_action = undefined;
      result.audit_entry.event = 'no_change';
      return result;
    }

    result.audit_entry = {
      ...baseAudit,
      event: 'milestone_updated',
      from_milestone: currentMilestone,
      to_milestone: newMilestone,
    };
  }

  return result;
}

// ─── Batch Reconciliation with Safety Checks ────────────────────────────────

export function reconcileBatch(
  records: Array<{ crm: CRMRecord; sf: SalesforceRecord }>,
): {
  results: ReconciliationResult[];
  batchWarnings: string[];
  shouldPause: boolean;
} {
  const results = records.map(({ crm, sf }) => reconcileLoanState(crm, sf));

  const transitionCount = results.filter(r => r.action === 'transition').length;
  const batchWarnings: string[] = [];
  let shouldPause = false;

  if (transitionCount > 50) {
    batchWarnings.push(
      `Bulk transition detected: ${transitionCount} records moving pipelines in one sync. ` +
      `Pausing for admin verification.`
    );
    shouldPause = true;
  }

  return { results, batchWarnings, shouldPause };
}
