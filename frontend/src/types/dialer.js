/**
 * Type definitions for dialer functionality
 * @fileoverview JSDoc type definitions for the Power Dialer feature
 */

/**
 * @typedef {'ACTIVE' | 'PAUSED' | 'STOPPED' | 'COMPLETED'} SessionStatus
 */

/**
 * @typedef {'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'NO_ANSWER' | 'FAILED' | 'SKIPPED'} TaskStatus
 */

/**
 * @typedef {'COMPLETED' | 'NO_ANSWER' | 'BUSY' | 'FAILED' | 'SKIPPED'} CallOutcome
 */

/**
 * @typedef {Object} ContactInfo
 * @property {string} name - Contact's name
 * @property {string} phone - Contact's phone number
 * @property {string} [context] - Optional context about the contact
 */

/**
 * @typedef {Object} CurrentTaskInfo
 * @property {string} task_id - Task ID
 * @property {string} name - Contact's name
 * @property {string} phone - Contact's phone number
 * @property {string} [context] - Optional context
 * @property {string} [call_sid] - Telnyx call SID if call is active
 */

/**
 * @typedef {Object} NextTaskPreview
 * @property {string} task_id - Task ID
 * @property {string} contact_name - Contact's name
 * @property {string} phone - Contact's phone number
 * @property {string} [context] - Optional context
 * @property {number} position - Position in queue
 */

/**
 * @typedef {Object} DialerSession
 * @property {string} session_id - Session ID
 * @property {SessionStatus} status - Current session status
 * @property {number} total_tasks - Total tasks in session
 * @property {number} completed_tasks - Completed tasks count
 * @property {number} failed_tasks - Failed tasks count
 * @property {number} skipped_tasks - Skipped tasks count
 * @property {CurrentTaskInfo} [current_task] - Current task being called
 * @property {NextTaskPreview[]} next_tasks - Upcoming tasks preview
 */

/**
 * @typedef {Object} DispositionFlags
 * @property {boolean} follow_up_required - Whether follow-up is needed
 * @property {boolean} referral_opportunity - Whether there's a referral opportunity
 * @property {boolean} appointment_set - Whether an appointment was set
 */

/**
 * @typedef {Object} DispositionRequest
 * @property {string} disposition - Disposition code
 * @property {string} [notes] - Optional notes
 * @property {string} [follow_up_date] - Optional follow-up date (ISO string)
 * @property {string} [voice_note_audio] - Base64 encoded voice note audio
 * @property {DispositionFlags} flags - Disposition flags
 */

/**
 * @typedef {Object} DispositionResponse
 * @property {boolean} success - Whether disposition was saved
 * @property {string} [ai_note_summary] - AI-generated summary of voice note
 * @property {Object} [task_created] - Task created from disposition
 * @property {string} task_created.id - Created task ID
 * @property {string} task_created.type - Task type (follow_up, referral)
 * @property {string} [task_created.due_date] - Task due date
 */

/**
 * @typedef {Object} WebSocketEvent
 * @property {string} type - Event type
 */

/**
 * @typedef {Object} DialerStatusEvent
 * @property {'dialer.status'} type - Event type
 * @property {string} session_id - Session ID
 * @property {SessionStatus} status - Session status
 * @property {string} [current_task_id] - Current task ID
 * @property {number} completed_tasks - Completed tasks count
 * @property {number} total_tasks - Total tasks count
 */

/**
 * @typedef {Object} DialerCallStartedEvent
 * @property {'dialer.call.started'} type - Event type
 * @property {string} session_id - Session ID
 * @property {string} task_id - Task ID
 * @property {string} call_sid - Telnyx call SID
 * @property {ContactInfo} contact - Contact being called
 */

/**
 * @typedef {Object} DialerCallCompletedEvent
 * @property {'dialer.call.completed'} type - Event type
 * @property {string} session_id - Session ID
 * @property {string} task_id - Task ID
 * @property {string} call_sid - Telnyx call SID
 * @property {number} duration_seconds - Call duration in seconds
 * @property {CallOutcome} outcome - Call outcome
 * @property {boolean} show_disposition_modal - Whether to show disposition modal
 */

/**
 * @typedef {Object} CallStatusUpdateEvent
 * @property {'call_status_update'} type - Event type
 * @property {string} session_id - Session ID
 * @property {string} task_id - Task ID
 * @property {string} call_sid - Telnyx call SID
 * @property {string} status - Telnyx call status
 * @property {number} duration_seconds - Call duration
 * @property {boolean} show_disposition_modal - Whether to show disposition modal
 */

/**
 * @typedef {Object} ClickToDialStatusEvent
 * @property {'click_to_dial_status'} type - Event type
 * @property {string} call_sid - Telnyx call SID
 * @property {string} status - Call status
 * @property {number} duration_seconds - Call duration
 * @property {string} to_number - Called number
 * @property {number} [call_log_id] - Call log ID
 * @property {boolean} show_disposition_modal - Whether to show disposition modal
 */

// Disposition options
export const DISPOSITION_OPTIONS = [
  { code: 'connected', label: 'Connected - Spoke with contact', category: 'success' },
  { code: 'voicemail', label: 'Left Voicemail', category: 'neutral' },
  { code: 'no_answer', label: 'No Answer', category: 'neutral' },
  { code: 'busy', label: 'Busy Signal', category: 'neutral' },
  { code: 'callback_scheduled', label: 'Callback Scheduled', category: 'success' },
  { code: 'not_interested', label: 'Not Interested', category: 'closed' },
  { code: 'wrong_number', label: 'Wrong Number', category: 'closed' },
  { code: 'do_not_call', label: 'Do Not Call Again', category: 'dnc' },
  { code: 'application_taken', label: 'Application Taken', category: 'success' },
  { code: 'referral_given', label: 'Referral Given', category: 'success' },
];

// Session status labels
export const SESSION_STATUS_LABELS = {
  ACTIVE: 'Active',
  PAUSED: 'Paused',
  STOPPED: 'Stopped',
  COMPLETED: 'Completed'
};

// Call outcome labels
export const CALL_OUTCOME_LABELS = {
  COMPLETED: 'Completed',
  NO_ANSWER: 'No Answer',
  BUSY: 'Busy',
  FAILED: 'Failed',
  SKIPPED: 'Skipped'
};
