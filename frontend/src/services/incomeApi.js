/**
 * Unified Income API Service
 *
 * Single canonical API service for ALL income operations:
 * - Income sources (CRUD)
 * - Income calculation (AI-assisted, smart-docs)
 * - Unified income calculator (14 types)
 * - Approval workflow (approve, reject, review, override)
 * - Document extraction (paystubs, bank statements)
 * - Verification tasks
 * - Form 1084 (preview, PDF, data)
 * - Analytics / stats
 * - Bank statement worksheets
 *
 * Replaces scattered fetch() calls and the narrower docIncomeApi.js.
 */

import { API_BASE_URL } from './api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build auth headers from the stored JWT token.
 * @returns {Record<string, string>}
 */
function getAuthHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Build auth headers without Content-Type (for blob downloads, FormData, etc.).
 * @returns {Record<string, string>}
 */
function getAuthHeadersRaw() {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Unwrap a fetch Response -- throw on non-2xx, return parsed JSON otherwise.
 * Provides human-readable messages for common HTTP status codes.
 * @param {Response} response
 * @returns {Promise<any>}
 */
async function handleResponse(response) {
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (response.status === 401) {
      throw new Error('Session expired. Please log in again.');
    }
    if (response.status === 403) {
      throw new Error(
        data?.detail || 'Access denied. You do not have permission for this action.',
      );
    }
    if (response.status === 429) {
      throw new Error('Too many requests. Please wait a moment and try again.');
    }
    const message =
      data?.detail || data?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return response.json();
}

// Route prefixes -----------------------------------------------------------

/** Core income routes (income_routes.py — prefix /api/v1/income) */
const INCOME = `${API_BASE_URL}/api/v1/income`;

/** Smart-docs income routes (smart_docs_income_routes.py — prefix /api/v1/smart-docs) */
const SMART_DOCS = `${API_BASE_URL}/api/v1/smart-docs`;

/** Unified income calculator routes (unified_income_routes.py — prefix /api/v1/unified-income) */
const UNIFIED = `${API_BASE_URL}/api/v1/unified-income`;

/** Form 1084 routes (form_1084_routes.py — prefix /api/v1/income/form-1084) */
const FORM_1084 = `${API_BASE_URL}/api/v1/income/form-1084`;

/** Bank statement routes (bank_statement_routes.py — prefix /api/v1/bank-statements) */
const BANK_STMT = `${API_BASE_URL}/api/v1/bank-statements`;

// ===========================================================================
// Income Sources
// ===========================================================================

/**
 * Get all income sources for a borrower.
 *
 * @param {number} borrowerId
 * @param {number|null} [loanId=null] - Optional loan filter
 * @param {boolean} [activeOnly=true] - Only return active sources
 * @returns {Promise<{borrower_id: number, count: number, sources: Object[]}>}
 */
export async function getIncomeSources(borrowerId, loanId = null, activeOnly = true) {
  const params = new URLSearchParams();
  if (loanId) params.set('loan_id', String(loanId));
  params.set('active_only', String(activeOnly));
  const qs = params.toString();

  const response = await fetch(
    `${INCOME}/borrowers/${borrowerId}/sources${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get all income sources for a loan (all borrowers).
 *
 * @param {number} loanId
 * @returns {Promise<{loan_id: number, count: number, sources: Object[]}>}
 */
export async function getLoanIncomeSources(loanId) {
  const response = await fetch(`${INCOME}/loans/${loanId}/sources`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get a single income source by ID.
 *
 * @param {number} sourceId
 * @returns {Promise<Object>} Income source object
 */
export async function getIncomeSource(sourceId) {
  const response = await fetch(`${INCOME}/sources/${sourceId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get income summary for a borrower on a specific loan.
 *
 * @param {number} borrowerId
 * @param {number} loanId
 * @returns {Promise<{borrower_id: number, loan_id: number, total_monthly_income: number, total_annual_income: number, source_count: number, verified_count: number, has_declining_income: boolean, sources: Object[]}>}
 */
export async function getIncomeSummary(borrowerId, loanId) {
  const response = await fetch(
    `${INCOME}/borrowers/${borrowerId}/summary?loan_id=${loanId}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get total qualifying income for a loan (all borrowers combined).
 *
 * @param {number} loanId
 * @returns {Promise<{loan_id: number, total_monthly_qualifying_income: number, total_annual_qualifying_income: number, by_borrower: Object}>}
 */
export async function getLoanQualifyingIncome(loanId) {
  const response = await fetch(`${INCOME}/loans/${loanId}/qualifying-income`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Create a new income source for a borrower.
 *
 * @param {number} borrowerId
 * @param {Object} sourceData
 * @param {number} sourceData.loan_id
 * @param {string} sourceData.income_type - e.g. "W2_EMPLOYMENT", "COMMISSION"
 * @param {string} [sourceData.source_name]
 * @param {string} [sourceData.source_description]
 * @param {boolean} [sourceData.is_primary]
 * @param {number} [sourceData.employment_id]
 * @returns {Promise<Object>} Created income source
 */
export async function createIncomeSource(borrowerId, sourceData) {
  const response = await fetch(`${INCOME}/borrowers/${borrowerId}/sources`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ borrower_id: borrowerId, ...sourceData }),
  });
  return handleResponse(response);
}

/**
 * Update an existing income source (partial update via PATCH).
 *
 * @param {number} sourceId
 * @param {Object} updates - Partial update fields
 * @param {string} [updates.source_name]
 * @param {number} [updates.monthly_qualifying_income]
 * @param {number} [updates.annual_qualifying_income]
 * @param {string} [updates.calculation_method]
 * @param {string} [updates.verification_status]
 * @param {string} [updates.verification_notes]
 * @param {boolean} [updates.is_primary]
 * @param {boolean} [updates.is_active]
 * @returns {Promise<Object>} Updated income source
 */
export async function updateIncomeSource(sourceId, updates) {
  const response = await fetch(`${INCOME}/sources/${sourceId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(updates),
  });
  return handleResponse(response);
}

/**
 * Delete (soft-deactivate) an income source.
 *
 * @param {number} sourceId
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function deleteIncomeSource(sourceId) {
  const response = await fetch(`${INCOME}/sources/${sourceId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Trigger per-source income calculation (e.g. from linked paystubs).
 *
 * @param {number} sourceId
 * @returns {Promise<Object>} Calculation result with monthly/annual income
 */
export async function calculateSourceIncome(sourceId) {
  const response = await fetch(`${INCOME}/sources/${sourceId}/calculate`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

// ===========================================================================
// Income Calculation (Smart Docs engine)
// ===========================================================================

/**
 * Run AI-powered income calculation for a loan/borrower pair.
 * Reads income documents, computes qualifying income, DTI ratios,
 * and generates verification tasks.
 *
 * @param {number} loanId
 * @param {number} borrowerId
 * @param {Object} [options={}] - Additional calculation options
 * @returns {Promise<{calculation: Object, sources: Object[], tasks: Object[], summary: Object}>}
 */
export async function calculateIncome(loanId, borrowerId, options = {}) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculate/${loanId}?borrower_id=${borrowerId}`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(options),
    },
  );
  return handleResponse(response);
}

/**
 * Re-run an existing calculation with the latest documents.
 * Supersedes the previous calculation.
 *
 * @param {number} calculationId
 * @returns {Promise<{calculation: Object, previous_calculation_id: number, summary: Object}>}
 */
export async function recalculateIncome(calculationId) {
  const response = await fetch(
    `${SMART_DOCS}/income/recalculate/${calculationId}`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
    },
  );
  return handleResponse(response);
}

/**
 * Get all income calculations for a loan, most recent first.
 *
 * @param {number} loanId
 * @returns {Promise<{loan_id: number, count: number, calculations: Object[]}>}
 */
export async function getCalculation(loanId) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculations/${loanId}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get calculation history (all calculations) for a loan.
 * Alias for getCalculation -- same endpoint returns full history.
 *
 * @param {number} loanId
 * @returns {Promise<{loan_id: number, count: number, calculations: Object[]}>}
 */
export async function getCalculationHistory(loanId) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculations/${loanId}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get full detail for a specific calculation including sources and tasks.
 *
 * @param {number} calculationId
 * @returns {Promise<{calculation: Object, sources: Object[], tasks: Object[]}>}
 */
export async function getCalculationDetail(calculationId) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get all income sources tied to a specific calculation.
 *
 * @param {number} calculationId
 * @returns {Promise<{calculation_id: number, loan_id: number, count: number, sources: Object[]}>}
 */
export async function getCalculationSources(calculationId) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}/sources`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

// ===========================================================================
// Unified Income Calculator (14 types)
// ===========================================================================

/**
 * Map of income type keys to their API slug.
 * @type {Record<string, string>}
 */
const INCOME_TYPE_SLUGS = {
  W2_HOURLY: 'w2-hourly',
  W2_SALARY: 'w2-salary',
  OT_BONUS: 'ot-bonus',
  COMMISSION: 'commission',
  NONTAX_SS: 'nontax-ss',
  NONTAX_OTHER: 'nontax-other',
  BANK_STATEMENT_PERSONAL: 'bank-statement-personal',
  BANK_STATEMENT_BUSINESS: 'bank-statement-business',
  RENTAL_SCHEDULE_E: 'rental-schedule-e',
  SELF_EMPLOYMENT_1084: 'self-employment-1084',
};

/**
 * Calculate a specific income type via the unified engine.
 *
 * @param {string} incomeType - Key from INCOME_TYPE_SLUGS (e.g. "W2_HOURLY", "COMMISSION")
 * @param {Object} data - Type-specific input data matching the backend request model
 * @returns {Promise<Object>} Calculation result with monthly/annual income, confidence, etc.
 */
export async function calculateUnifiedIncome(incomeType, data) {
  const slug = INCOME_TYPE_SLUGS[incomeType];
  if (!slug) {
    throw new Error(
      `Unknown income type "${incomeType}". Valid types: ${Object.keys(INCOME_TYPE_SLUGS).join(', ')}`,
    );
  }
  const response = await fetch(`${UNIFIED}/calculate/${slug}`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

/**
 * Detect income document type from OCR text.
 *
 * @param {string} text - OCR or extracted text from document
 * @param {string} [filename] - Optional filename for additional detection hints
 * @returns {Promise<{document_type: string, confidence: number, suggested_income_type: string, extracted_fields: Object}>}
 */
export async function detectIncomeDocument(text, filename = null) {
  const response = await fetch(`${UNIFIED}/detect`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ text, filename }),
  });
  return handleResponse(response);
}

/**
 * Get the list of supported document and income types.
 *
 * @returns {Promise<{document_types: string[], income_types: string[]}>}
 */
export async function getDocumentTypes() {
  const response = await fetch(`${UNIFIED}/document-types`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get required documents for a specific income type.
 *
 * @param {string} incomeType - e.g. "w2_hourly", "commission"
 * @returns {Promise<{income_type: string, required_documents: string[]}>}
 */
export async function getRequiredDocuments(incomeType) {
  const response = await fetch(`${UNIFIED}/required-documents/${incomeType}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Process a document through the complete unified workflow:
 * detect type -> extract fields -> calculate income -> review/auto-approve.
 *
 * Uses FormData because the backend endpoint accepts Form(...) parameters.
 *
 * @param {number} loanId
 * @param {number} borrowerId
 * @param {string} documentText - OCR text
 * @param {string} [documentFilename]
 * @param {string} [documentId]
 * @returns {Promise<Object>} Review item result
 */
export async function processDocument(loanId, borrowerId, documentText, documentFilename = null, documentId = null) {
  const body = new FormData();
  body.append('loan_id', String(loanId));
  body.append('borrower_id', String(borrowerId));
  body.append('document_text', documentText);
  if (documentFilename) body.append('document_filename', documentFilename);
  if (documentId) body.append('document_id', documentId);

  const response = await fetch(`${UNIFIED}/process-document`, {
    method: 'POST',
    headers: getAuthHeadersRaw(), // No Content-Type -- FormData sets its own
    body,
  });
  return handleResponse(response);
}

/**
 * Get items pending review in the unified review queue.
 *
 * @param {Object} [filters={}]
 * @param {number} [filters.loanId] - Filter by loan
 * @param {string} [filters.reviewer] - Filter by reviewer name
 * @param {number} [filters.minConfidence] - Min confidence score (0-100)
 * @param {number} [filters.maxConfidence] - Max confidence score (0-100)
 * @returns {Promise<{count: number, items: Object[]}>}
 */
export async function getReviewQueue(filters = {}) {
  const params = new URLSearchParams();
  if (filters.loanId) params.set('loan_id', String(filters.loanId));
  if (filters.reviewer) params.set('reviewer', filters.reviewer);
  if (filters.minConfidence != null) params.set('min_confidence', String(filters.minConfidence));
  if (filters.maxConfidence != null) params.set('max_confidence', String(filters.maxConfidence));
  const qs = params.toString();

  const response = await fetch(
    `${UNIFIED}/review/queue${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Get summary of the unified review queue status.
 *
 * @returns {Promise<{pending_review: number, in_review: number, revision_requested: number, auto_approved_today: number, approved_today: number, rejected_today: number, average_confidence: number, oldest_pending_hours: number}>}
 */
export async function getReviewQueueSummary() {
  const response = await fetch(`${UNIFIED}/review/queue/summary`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get a specific review item by ID.
 *
 * @param {string} itemId
 * @returns {Promise<Object>} Review item details
 */
export async function getReviewItem(itemId) {
  const response = await fetch(`${UNIFIED}/review/item/${itemId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get complete review history for a specific item.
 *
 * @param {string} itemId
 * @returns {Promise<{history: Object[]}>}
 */
export async function getReviewHistory(itemId) {
  const response = await fetch(`${UNIFIED}/review/item/${itemId}/history`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Perform a review action (approve, reject, request_revision) on a unified review item.
 *
 * @param {Object} action
 * @param {string} action.item_id - Review item ID
 * @param {string} action.action - "approve" | "reject" | "request_revision"
 * @param {string} action.reviewer - Reviewer name
 * @param {string} [action.comment] - Comment (required for reject)
 * @param {number} [action.override_monthly] - Override monthly amount (approve only)
 * @param {number} [action.override_annual] - Override annual amount (approve only)
 * @param {string} [action.revision_notes] - Notes (required for request_revision)
 * @returns {Promise<Object>} Updated review item
 */
export async function performReviewAction(action) {
  const response = await fetch(`${UNIFIED}/review/action`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(action),
  });
  return handleResponse(response);
}

/**
 * Get complete income status for a loan (unified orchestrator view).
 *
 * @param {number} loanId
 * @returns {Promise<Object>} Full income status with all sources and review items
 */
export async function getLoanIncomeStatus(loanId) {
  const response = await fetch(`${UNIFIED}/loan/${loanId}/income`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get only approved income for a loan with totals.
 *
 * @param {number} loanId
 * @returns {Promise<{loan_id: number, total_monthly: number, total_annual: number, income_sources: Object[]}>}
 */
export async function getApprovedIncome(loanId) {
  const response = await fetch(`${UNIFIED}/loan/${loanId}/income/approved`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

// ===========================================================================
// Approval Workflow (Smart Docs calculation-level)
// ===========================================================================

/**
 * Submit an income calculation for review (pre-approval step).
 * Enforces maker-checker: reviewer cannot be the calculator.
 *
 * @param {number} calculationId
 * @param {string} [notes=''] - Optional review notes
 * @returns {Promise<{status: string, calculation_id: number, reviewed_by: string, reviewed_at: string, calculation: Object}>}
 */
export async function submitForReview(calculationId, notes = '') {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}/review`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ notes }),
    },
  );
  return handleResponse(response);
}

/**
 * Approve an income calculation.
 * Enforces maker-checker: cannot approve your own calculation.
 *
 * @param {number} calculationId
 * @param {string} [notes=''] - Optional approval notes
 * @param {boolean} [adminOverride=false] - Platform admin override for separation-of-duties
 * @returns {Promise<{status: string, calculation_id: number, approved_by: string, approved_at: string, admin_override: boolean, calculation: Object}>}
 */
export async function approveIncome(calculationId, notes = '', adminOverride = false) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}/approve`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ notes, admin_override: adminOverride }),
    },
  );
  return handleResponse(response);
}

/**
 * Reject an income calculation with a reason.
 *
 * @param {number} calculationId
 * @param {string} reason - Required rejection reason
 * @param {string} [notes=''] - Additional notes
 * @returns {Promise<{status: string, calculation_id: number, reason: string, rejected_by: string, rejected_at: string, calculation: Object}>}
 */
export async function rejectIncome(calculationId, reason, notes = '') {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}/reject`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ reason, notes }),
    },
  );
  return handleResponse(response);
}

/**
 * Override an income source amount (manual override with full audit trail).
 * Override_by is always set from the authenticated user on the backend.
 *
 * @param {number} sourceId
 * @param {Object} override
 * @param {number} override.monthlyAmount - New monthly amount
 * @param {number} override.annualAmount - New annual amount
 * @param {string} override.reason - Required reason for override
 * @returns {Promise<{status: string, source_id: number, previous_monthly: number, previous_annual: number, new_monthly: number, new_annual: number, override_by: string, reason: string, source: Object}>}
 */
export async function overrideSource(sourceId, { monthlyAmount, annualAmount, reason }) {
  const response = await fetch(
    `${SMART_DOCS}/income/source/${sourceId}/override`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        monthly_amount: monthlyAmount,
        annual_amount: annualAmount,
        reason,
      }),
    },
  );
  return handleResponse(response);
}

/**
 * Generate an income report (PDF) for a calculation. Returns a pre-signed S3 URL.
 *
 * @param {number} calculationId
 * @returns {Promise<{calculation_id: number, loan_id: number, report_url: string, generated_at: string}>}
 */
export async function getIncomeReport(calculationId) {
  const response = await fetch(
    `${SMART_DOCS}/income/calculation/${calculationId}/report`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

// ===========================================================================
// Document Extraction
// ===========================================================================

/**
 * Extract income data from uploaded documents for a specific income type.
 * Creates or updates income source with extracted values.
 *
 * @param {number} loanId
 * @param {number} borrowerId
 * @param {string} incomeType - e.g. "W2_EMPLOYMENT", "BANK_STATEMENT", "SELF_EMPLOYED_SCHEDULE_C"
 * @returns {Promise<{success: boolean, message: string, source_id: number, source_name: string, monthly_income: number, annual_income: number, extracted_fields: string[]}>}
 */
export async function extractFromDocuments(loanId, borrowerId, incomeType) {
  const response = await fetch(`${INCOME}/extract-from-documents`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      loan_id: loanId,
      borrower_id: borrowerId,
      income_type: incomeType,
    }),
  });
  return handleResponse(response);
}

/**
 * Get all extracted income data for a loan, organized by income type.
 *
 * @param {number} loanId
 * @returns {Promise<{extractions: Object}>}
 */
export async function getLoanExtractions(loanId) {
  const response = await fetch(`${INCOME}/loan/${loanId}/extractions`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Extract paystub data from a specific document using AI.
 * The document must exist in the smart_documents table.
 *
 * @param {number} documentId - SmartDocument ID
 * @returns {Promise<{success: boolean, extraction_id: number, document_id: number, extracted_data: Object}>}
 */
export async function extractPaystubFromDocument(documentId) {
  const response = await fetch(`${INCOME}/documents/${documentId}/extract`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get a specific paystub extraction by ID.
 *
 * @param {number} extractionId
 * @returns {Promise<Object>} Full paystub extraction with employer, employee, earnings, YTD data
 */
export async function getPaystubExtraction(extractionId) {
  const response = await fetch(`${INCOME}/extractions/${extractionId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get all extractions for a document.
 *
 * @param {number} documentId
 * @returns {Promise<{document_id: number, count: number, extractions: Object[]}>}
 */
export async function getDocumentExtractions(documentId) {
  const response = await fetch(
    `${INCOME}/documents/${documentId}/extractions`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Apply extracted paystub data to borrower profile.
 * Creates/updates employment and income source records.
 *
 * @param {number} extractionId
 * @param {string[]} fieldsToApply - Field names to apply (e.g. ["employer_address_line1", "hire_date", "hourly_rate"])
 * @param {boolean} [createEmployment=true] - Create/update employment record
 * @param {boolean} [createIncomeSource=true] - Create/update income source record
 * @returns {Promise<{success: boolean, extraction_id: number, applied: {employment_id: number|null, income_source_id: number|null, fields_applied: string[]}}>}
 */
export async function applyExtraction(
  extractionId,
  fieldsToApply,
  createEmployment = true,
  createIncomeSource = true,
) {
  const response = await fetch(`${INCOME}/apply-extraction`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      extraction_id: extractionId,
      fields_to_apply: fieldsToApply,
      create_employment: createEmployment,
      create_income_source: createIncomeSource,
    }),
  });
  return handleResponse(response);
}

// ===========================================================================
// Verification Tasks
// ===========================================================================

/**
 * Get all income verification tasks for a loan.
 *
 * @param {number} loanId
 * @param {string} [status] - Filter: "OPEN", "IN_PROGRESS", "COMPLETED", "DEFERRED"
 * @returns {Promise<{loan_id: number, count: number, tasks: Object[]}>}
 */
export async function getVerificationTasks(loanId, status = null) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  const qs = params.toString();

  const response = await fetch(
    `${SMART_DOCS}/income/tasks/${loanId}${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Complete a verification task.
 *
 * @param {number} taskId
 * @param {string} resolvedBy - Name or identifier of who resolved the task
 * @param {string} [resolutionNotes] - Optional resolution notes
 * @returns {Promise<{status: string, task_id: number, resolved_by: string, resolved_at: string, task: Object}>}
 */
export async function completeTask(taskId, resolvedBy, resolutionNotes = null) {
  const response = await fetch(
    `${SMART_DOCS}/income/tasks/${taskId}/complete`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        resolved_by: resolvedBy,
        resolution_notes: resolutionNotes,
      }),
    },
  );
  return handleResponse(response);
}

/**
 * Defer a verification task with a reason and optional resume date.
 *
 * @param {number} taskId
 * @param {string} reason - Required reason for deferral
 * @param {string} [deferUntil] - ISO-8601 date string for when to resume
 * @returns {Promise<{status: string, task_id: number, reason: string, defer_until: string|null, task: Object}>}
 */
export async function deferTask(taskId, reason, deferUntil = null) {
  const response = await fetch(
    `${SMART_DOCS}/income/tasks/${taskId}/defer`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        reason,
        defer_until: deferUntil,
      }),
    },
  );
  return handleResponse(response);
}

// ===========================================================================
// Form 1084
// ===========================================================================

/**
 * Get Form 1084 preview as structured JSON (includes rendered HTML + metadata).
 *
 * @param {number} loanId
 * @param {number} [calculationId] - Specific calculation; omit for latest
 * @returns {Promise<{html: string, borrower_name: string, loan_number: string, total_qualifying_monthly: number, total_qualifying_annual: number, generated_at: string, sections: Object[]}>}
 */
export async function getForm1084Preview(loanId, calculationId = null) {
  const params = new URLSearchParams();
  if (calculationId) params.set('calculation_id', String(calculationId));
  const qs = params.toString();

  const response = await fetch(
    `${FORM_1084}/${loanId}/preview${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

/**
 * Download Form 1084 as a PDF. Triggers a browser file download.
 *
 * @param {number} loanId
 * @param {Object} [options={}]
 * @param {number} [options.calculationId] - Specific calculation ID
 * @param {boolean} [options.includeNotes=true] - Include notes in PDF
 * @param {boolean} [options.includeFlags=true] - Include AI flags in PDF
 * @returns {Promise<void>}
 */
export async function downloadForm1084(loanId, options = {}) {
  const body = {};
  if (options.calculationId) body.calculation_id = options.calculationId;
  if (options.includeNotes !== undefined) body.include_notes = options.includeNotes;
  if (options.includeFlags !== undefined) body.include_flags = options.includeFlags;

  const response = await fetch(`${FORM_1084}/${loanId}/generate`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Failed to generate Form 1084');
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `Form_1084_${loanId}_${new Date().toISOString().slice(0, 10)}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Get Form 1084 raw structured data as JSON.
 * Useful for custom UI rendering or data export.
 *
 * @param {number} loanId
 * @param {number} [calculationId] - Specific calculation; omit for latest
 * @returns {Promise<Object>} Full Form 1084 data (loan_id, calculation_id, borrower_name, sections, DTI, flags, etc.)
 */
export async function getForm1084Data(loanId, calculationId = null) {
  const params = new URLSearchParams();
  if (calculationId) params.set('calculation_id', String(calculationId));
  const qs = params.toString();

  const response = await fetch(
    `${FORM_1084}/${loanId}/data${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

// ===========================================================================
// Analytics
// ===========================================================================

/**
 * Get aggregate income calculation statistics for the current user's org.
 * Includes status breakdown, average DTI, confidence scores, and auto-approval rate.
 *
 * @returns {Promise<{total_calculations: number, status_breakdown: Object, averages: Object, dti_distribution: Object, auto_approval_rate: number}>}
 */
export async function getIncomeAnalytics() {
  const response = await fetch(`${SMART_DOCS}/income/stats`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

// ===========================================================================
// Bank Statement Worksheets
// ===========================================================================

/**
 * Create a new bank statement worksheet for a loan.
 * Returns the existing worksheet if one already exists for the loan/borrower pair.
 *
 * @param {Object} worksheetData
 * @param {number} worksheetData.loan_id
 * @param {number} worksheetData.borrower_id
 * @param {string} [worksheetData.borrower_name]
 * @param {string} [worksheetData.business_name]
 * @param {number} [worksheetData.ownership_percentage=100]
 * @param {number} [worksheetData.months_of_statements=12]
 * @param {string} [worksheetData.calculation_method="UNIFORM_EXPENSE_RATIO"]
 * @param {number} [worksheetData.ltv_percentage=80]
 * @param {number} [worksheetData.cpa_expense_ratio]
 * @param {boolean} [worksheetData.has_separate_business_account=false]
 * @returns {Promise<{success: boolean, message: string, worksheet_id: number}>}
 */
export async function createWorksheet(worksheetData) {
  const response = await fetch(`${BANK_STMT}/worksheets`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(worksheetData),
  });
  return handleResponse(response);
}

/**
 * Get a bank statement worksheet by ID with all account and monthly data.
 *
 * @param {number} worksheetId
 * @returns {Promise<Object>} Full worksheet with accounts array, each containing monthly_data
 */
export async function getWorksheet(worksheetId) {
  const response = await fetch(`${BANK_STMT}/worksheets/${worksheetId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Get worksheet for a specific loan (checks if one exists).
 *
 * @param {number} loanId
 * @returns {Promise<{exists: boolean, worksheet_id?: number, status?: string, calculated_monthly_income?: number}>}
 */
export async function getWorksheetByLoan(loanId) {
  const response = await fetch(`${BANK_STMT}/loan/${loanId}/worksheet`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

/**
 * Extract bank statement data from uploaded documents using AI.
 *
 * @param {number} worksheetId
 * @param {number[]} documentIds - Array of SmartDocument IDs
 * @param {string} [statementType="PERSONAL"] - "PERSONAL" or "BUSINESS"
 * @returns {Promise<{success: boolean, message: string, months_extracted: number, calculated_monthly_income: number, calculated_annual_income: number}>}
 */
export async function extractBankStatements(worksheetId, documentIds, statementType = 'PERSONAL') {
  const response = await fetch(`${BANK_STMT}/worksheets/${worksheetId}/extract`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      document_ids: documentIds,
      statement_type: statementType,
    }),
  });
  return handleResponse(response);
}

/**
 * Download a bank statement worksheet as an Excel file.
 * Triggers a browser file download.
 *
 * @param {number} worksheetId
 * @returns {Promise<void>}
 */
export async function downloadWorksheetExcel(worksheetId) {
  const response = await fetch(
    `${BANK_STMT}/worksheets/${worksheetId}/download`,
    { headers: getAuthHeadersRaw() },
  );

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || 'Failed to download worksheet');
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  // Extract filename from Content-Disposition header if available
  const disposition = response.headers.get('Content-Disposition');
  let filename = `Bank_Statement_Worksheet_${worksheetId}.xlsx`;
  if (disposition) {
    const match = disposition.match(/filename="?(.+?)"?$/);
    if (match) filename = match[1];
  }

  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ===========================================================================
// Employment Records
// ===========================================================================

/**
 * Get all employment records for a borrower.
 *
 * @param {number} borrowerId
 * @param {number} [loanId] - Optional loan filter
 * @returns {Promise<{borrower_id: number, count: number, employments: Object[]}>}
 */
export async function getBorrowerEmployments(borrowerId, loanId = null) {
  const params = new URLSearchParams();
  if (loanId) params.set('loan_id', String(loanId));
  const qs = params.toString();

  const response = await fetch(
    `${INCOME}/borrowers/${borrowerId}/employments${qs ? `?${qs}` : ''}`,
    { headers: getAuthHeaders() },
  );
  return handleResponse(response);
}

// ===========================================================================
// Convenience bundle export
// ===========================================================================

/**
 * All methods bundled as a single object for default-import or namespace usage.
 * @example
 *   import incomeAPI from '../services/incomeApi';
 *   const sources = await incomeAPI.getIncomeSources(borrowerId);
 */
export const incomeAPI = {
  // Income Sources
  getIncomeSources,
  getLoanIncomeSources,
  getIncomeSource,
  getIncomeSummary,
  getLoanQualifyingIncome,
  createIncomeSource,
  updateIncomeSource,
  deleteIncomeSource,
  calculateSourceIncome,

  // Income Calculation (Smart Docs)
  calculateIncome,
  recalculateIncome,
  getCalculation,
  getCalculationHistory,
  getCalculationDetail,
  getCalculationSources,

  // Unified Income Calculator (14 types)
  calculateUnifiedIncome,
  detectIncomeDocument,
  getDocumentTypes,
  getRequiredDocuments,
  processDocument,
  getReviewQueue,
  getReviewQueueSummary,
  getReviewItem,
  getReviewHistory,
  performReviewAction,
  getLoanIncomeStatus,
  getApprovedIncome,

  // Approval Workflow
  submitForReview,
  approveIncome,
  rejectIncome,
  overrideSource,
  getIncomeReport,

  // Document Extraction
  extractFromDocuments,
  getLoanExtractions,
  extractPaystubFromDocument,
  getPaystubExtraction,
  getDocumentExtractions,
  applyExtraction,

  // Verification Tasks
  getVerificationTasks,
  completeTask,
  deferTask,

  // Form 1084
  getForm1084Preview,
  downloadForm1084,
  getForm1084Data,

  // Analytics
  getIncomeAnalytics,

  // Bank Statement Worksheets
  createWorksheet,
  getWorksheet,
  getWorksheetByLoan,
  extractBankStatements,
  downloadWorksheetExcel,

  // Employment
  getBorrowerEmployments,
};

export default incomeAPI;
