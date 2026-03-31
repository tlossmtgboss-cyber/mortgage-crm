/**
 * Conflict Resolver Service
 *
 * Detects and manages conflicts between offline mutations and server state.
 * When a user makes changes while offline and the server has been updated
 * in the meantime, this service stores the conflict and provides resolution
 * strategies: keep local, keep server, or field-by-field merge.
 *
 * Conflicts are persisted in localStorage so they survive app restarts.
 */

const STORAGE_KEY = 'perennia_conflicts';

// ============================================================================
// CONFLICT RECORD
// ============================================================================

/**
 * @typedef {Object} ConflictRecord
 * @property {string} id - Unique conflict ID
 * @property {'lead' | 'loan' | 'task' | 'note'} entityType
 * @property {string} entityId - ID of the conflicting entity
 * @property {string} entityLabel - Human-readable label (borrower name, task title, etc.)
 * @property {Object} localChanges - Field values from the offline mutation
 * @property {Object} serverState - Current field values on the server
 * @property {string[]} conflictFields - Fields that differ between local and server
 * @property {number} createdAt - Timestamp when conflict was detected
 * @property {'unresolved' | 'resolved'} status
 * @property {string|null} resolvedAt - Timestamp when resolved
 * @property {string|null} resolution - How it was resolved: 'keep_local' | 'keep_server' | 'merge'
 */

/**
 * Generate a short unique ID for conflict records.
 */
function generateId() {
  return `conflict_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

// ============================================================================
// PERSISTENCE
// ============================================================================

function loadConflicts() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (err) {
    console.error('Failed to load conflicts from storage:', err);
    return [];
  }
}

function saveConflicts(conflicts) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conflicts));
  } catch (err) {
    console.error('Failed to save conflicts to storage:', err);
  }
}

// ============================================================================
// CHANGE LISTENERS
// ============================================================================

const listeners = new Set();

/**
 * Subscribe to conflict list changes. Returns an unsubscribe function.
 */
export function onConflictsChanged(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function notifyListeners() {
  const conflicts = loadConflicts();
  listeners.forEach((cb) => {
    try {
      cb(conflicts);
    } catch (err) {
      console.error('Conflict listener error:', err);
    }
  });
}

// ============================================================================
// DETECTION
// ============================================================================

/**
 * Detect whether a server response represents a conflict.
 *
 * Returns true for:
 * - HTTP 409 Conflict responses
 * - Responses where the server entity's updated_at is newer than the
 *   offline mutation's createdAt timestamp
 *
 * @param {Object} serverResponse - Axios response or fetch Response-like object
 * @param {Object} [offlineMutation] - The queued mutation with a createdAt timestamp
 * @returns {boolean}
 */
export function detectConflict(serverResponse, offlineMutation) {
  // HTTP 409 is an explicit conflict signal
  const status = serverResponse?.status || serverResponse?.response?.status;
  if (status === 409) {
    return true;
  }

  // Timestamp comparison: if the server entity was updated after
  // the offline mutation was created, the data has diverged
  if (offlineMutation?.createdAt && serverResponse?.data) {
    const serverUpdatedAt = serverResponse.data.updated_at || serverResponse.data.updatedAt;
    if (serverUpdatedAt) {
      const serverTime = new Date(serverUpdatedAt).getTime();
      const mutationTime = typeof offlineMutation.createdAt === 'number'
        ? offlineMutation.createdAt
        : new Date(offlineMutation.createdAt).getTime();

      if (serverTime > mutationTime) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Compute which fields actually differ between local and server objects.
 *
 * @param {Object} localChanges - Fields the user changed offline
 * @param {Object} serverState - Current server state for those fields
 * @returns {string[]} List of field names that differ
 */
export function findConflictFields(localChanges, serverState) {
  const fields = [];
  for (const key of Object.keys(localChanges)) {
    const localVal = localChanges[key];
    const serverVal = serverState[key];

    // Normalize nullish values for comparison
    const normalizedLocal = localVal === undefined ? null : localVal;
    const normalizedServer = serverVal === undefined ? null : serverVal;

    if (JSON.stringify(normalizedLocal) !== JSON.stringify(normalizedServer)) {
      fields.push(key);
    }
  }
  return fields;
}

// ============================================================================
// CONFLICT CRUD
// ============================================================================

/**
 * Create and store a new conflict record.
 *
 * @param {Object} params
 * @param {'lead' | 'loan' | 'task' | 'note'} params.entityType
 * @param {string} params.entityId
 * @param {string} [params.entityLabel] - Human-readable label for the entity
 * @param {Object} params.localChanges - The offline mutation's field values
 * @param {Object} params.serverState - The current server state
 * @returns {ConflictRecord} The created conflict record
 */
export function createConflict({ entityType, entityId, entityLabel, localChanges, serverState }) {
  const conflictFields = findConflictFields(localChanges, serverState);

  // If there are no actual field-level differences, skip
  if (conflictFields.length === 0) {
    return null;
  }

  const conflict = {
    id: generateId(),
    entityType,
    entityId,
    entityLabel: entityLabel || `${entityType} ${entityId.slice(0, 8)}`,
    localChanges,
    serverState,
    conflictFields,
    createdAt: Date.now(),
    status: 'unresolved',
    resolvedAt: null,
    resolution: null,
  };

  const conflicts = loadConflicts();
  conflicts.push(conflict);
  saveConflicts(conflicts);
  notifyListeners();

  return conflict;
}

/**
 * Get all conflict records.
 *
 * @returns {ConflictRecord[]}
 */
export function getAllConflicts() {
  return loadConflicts();
}

/**
 * Get only unresolved conflict records.
 *
 * @returns {ConflictRecord[]}
 */
export function getUnresolvedConflicts() {
  return loadConflicts().filter((c) => c.status === 'unresolved');
}

/**
 * Get a single conflict by ID.
 *
 * @param {string} conflictId
 * @returns {ConflictRecord|null}
 */
export function getConflictById(conflictId) {
  return loadConflicts().find((c) => c.id === conflictId) || null;
}

// ============================================================================
// RESOLUTION
// ============================================================================

/**
 * Build the merged data object for a given resolution strategy.
 *
 * @param {ConflictRecord} conflict
 * @param {'keep_local' | 'keep_server' | 'merge'} resolution
 * @param {Object} [mergedFields] - For 'merge' resolution: object mapping field names
 *   to the chosen value. Each field should have either the local or server value.
 * @returns {Object} The final data object to submit to the server
 */
export function buildResolvedData(conflict, resolution, mergedFields) {
  switch (resolution) {
    case 'keep_local':
      // Use all local changes on top of server state
      return { ...conflict.serverState, ...conflict.localChanges };

    case 'keep_server':
      // Discard local changes entirely
      return { ...conflict.serverState };

    case 'merge':
      if (!mergedFields || typeof mergedFields !== 'object') {
        throw new Error('mergedFields is required for merge resolution');
      }
      // Start with server state, overlay the cherry-picked merged fields
      return { ...conflict.serverState, ...mergedFields };

    default:
      throw new Error(`Unknown resolution strategy: ${resolution}`);
  }
}

/**
 * Resolve a conflict.
 *
 * Marks the conflict as resolved and returns the data object that should
 * be submitted to the server as a force-update.
 *
 * @param {string} conflictId
 * @param {'keep_local' | 'keep_server' | 'merge'} resolution
 * @param {Object} [mergedFields] - Required when resolution is 'merge'
 * @returns {{ conflict: ConflictRecord, resolvedData: Object }}
 */
export function resolveConflict(conflictId, resolution, mergedFields) {
  const conflicts = loadConflicts();
  const index = conflicts.findIndex((c) => c.id === conflictId);

  if (index === -1) {
    throw new Error(`Conflict ${conflictId} not found`);
  }

  const conflict = conflicts[index];
  const resolvedData = buildResolvedData(conflict, resolution, mergedFields);

  // Mark resolved
  conflict.status = 'resolved';
  conflict.resolvedAt = Date.now();
  conflict.resolution = resolution;

  conflicts[index] = conflict;
  saveConflicts(conflicts);
  notifyListeners();

  return { conflict, resolvedData };
}

/**
 * Resolve all unresolved conflicts with the same strategy.
 *
 * @param {'keep_local' | 'keep_server'} resolution - Batch only supports keep_local or keep_server
 * @returns {{ resolved: Array<{ conflict: ConflictRecord, resolvedData: Object }> }}
 */
export function resolveAllConflicts(resolution) {
  if (resolution === 'merge') {
    throw new Error('Batch resolve does not support merge — each conflict needs individual field picks');
  }

  const conflicts = loadConflicts();
  const resolved = [];

  for (let i = 0; i < conflicts.length; i++) {
    if (conflicts[i].status !== 'unresolved') continue;

    const resolvedData = buildResolvedData(conflicts[i], resolution);
    conflicts[i].status = 'resolved';
    conflicts[i].resolvedAt = Date.now();
    conflicts[i].resolution = resolution;

    resolved.push({ conflict: conflicts[i], resolvedData });
  }

  saveConflicts(conflicts);
  notifyListeners();

  return { resolved };
}

/**
 * Remove all resolved conflicts from storage (cleanup).
 *
 * @returns {number} Number of records removed
 */
export function purgeResolvedConflicts() {
  const conflicts = loadConflicts();
  const remaining = conflicts.filter((c) => c.status !== 'resolved');
  const removed = conflicts.length - remaining.length;
  saveConflicts(remaining);
  notifyListeners();
  return removed;
}

/**
 * Clear all conflicts (for testing or hard reset).
 */
export function clearAllConflicts() {
  saveConflicts([]);
  notifyListeners();
}

// ============================================================================
// FIELD DISPLAY HELPERS
// ============================================================================

/**
 * Human-readable label for entity types.
 */
export const ENTITY_TYPE_LABELS = {
  lead: 'Lead',
  loan: 'Loan',
  task: 'Task',
  note: 'Note',
};

/**
 * Human-readable labels for common CRM field names.
 */
export const FIELD_LABELS = {
  // Lead fields
  first_name: 'First Name',
  last_name: 'Last Name',
  email: 'Email',
  phone: 'Phone',
  stage: 'Stage',
  source: 'Source',
  ai_score: 'AI Score',
  loan_purpose: 'Loan Purpose',
  loan_amount: 'Loan Amount',
  credit_score: 'Credit Score',
  property_type: 'Property Type',
  notes: 'Notes',

  // Loan fields
  borrower_name: 'Borrower Name',
  borrower_email: 'Borrower Email',
  amount: 'Loan Amount',
  rate: 'Rate',
  loan_type: 'Loan Type',
  loan_number: 'Loan Number',
  property_address: 'Property Address',
  closing_date: 'Closing Date',
  lock_expiration_date: 'Lock Expiration',

  // Task fields
  title: 'Title',
  description: 'Description',
  status: 'Status',
  priority: 'Priority',
  due_date: 'Due Date',
  assigned_to: 'Assigned To',

  // Note fields
  content: 'Content',
  subject: 'Subject',
};

/**
 * Get a display-friendly label for a field name.
 *
 * @param {string} fieldName
 * @returns {string}
 */
export function getFieldLabel(fieldName) {
  return FIELD_LABELS[fieldName] || fieldName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Format a field value for display. Handles dates, currency, booleans, nulls.
 *
 * @param {*} value
 * @param {string} fieldName
 * @returns {string}
 */
export function formatFieldValue(value, fieldName) {
  if (value === null || value === undefined) return '(empty)';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';

  // Currency fields
  if (['amount', 'loan_amount', 'preapproval_amount'].includes(fieldName)) {
    const num = parseFloat(value);
    if (!isNaN(num)) return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
  }

  // Rate fields
  if (['rate'].includes(fieldName)) {
    const num = parseFloat(value);
    if (!isNaN(num)) return `${num.toFixed(3)}%`;
  }

  // Date fields
  if (['closing_date', 'due_date', 'lock_expiration_date', 'created_at', 'updated_at'].includes(fieldName)) {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return d.toLocaleDateString('en-US');
  }

  return String(value);
}
