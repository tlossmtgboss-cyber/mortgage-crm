/**
 * Notification Action Category Handlers
 *
 * Routes users to the correct screen when they tap a push notification.
 * Each notification category defines a default action and optional quick actions.
 * Integrates with the native haptic feedback system from nativeServices.js.
 */

import { haptics } from './nativeServices';

// ============================================================================
// INTERNAL STATE
// ============================================================================

let _navigate = null;
let _apiClient = null;

/**
 * Initialize the notification action system.
 * Must be called once with the router navigate function (from react-router).
 *
 * @param {Function} navigate - react-router navigate function
 * @param {Object} [apiClient] - optional API client for quick actions (send reminder, etc.)
 */
export function initNotificationActions(navigate, apiClient = null) {
  _navigate = navigate;
  _apiClient = apiClient;
}

// ============================================================================
// NOTIFICATION CATEGORIES
// ============================================================================

/**
 * All notification category definitions.
 * Each category has:
 *   - type: the string identifier sent in notification.data.type
 *   - label: human-readable name
 *   - defaultRoute: function(data) returning the route path
 *   - quickActions: array of { id, label, handler(data) }
 */
export const NOTIFICATION_CATEGORIES = {
  LOAN_UPDATE: {
    type: 'LOAN_UPDATE',
    label: 'Loan Update',
    description: 'Loan stage changed, condition added, or document received',
    defaultRoute: (data) => `/loans/${data.loanId || data.loan_id || data.entityId}`,
    quickActions: [
      {
        id: 'view_loan',
        label: 'View Loan',
        handler: (data) => {
          navigateTo(`/loans/${data.loanId || data.loan_id || data.entityId}`);
        },
      },
      {
        id: 'call_borrower',
        label: 'Call Borrower',
        handler: (data) => {
          if (data.borrowerPhone || data.borrower_phone) {
            const phone = (data.borrowerPhone || data.borrower_phone).replace(/[^\d+]/g, '');
            window.open(`tel:${phone}`, '_self');
          } else {
            // Fall back to loan detail where phone is accessible
            navigateTo(`/loans/${data.loanId || data.loan_id || data.entityId}`);
          }
        },
      },
    ],
  },

  LEAD_NEW: {
    type: 'LEAD_NEW',
    label: 'New Lead',
    description: 'New lead assigned to you',
    defaultRoute: (data) => `/leads/${data.leadId || data.lead_id || data.entityId}`,
    quickActions: [
      {
        id: 'call_now',
        label: 'Call Now',
        handler: (data) => {
          if (data.leadPhone || data.lead_phone || data.phone) {
            const phone = (data.leadPhone || data.lead_phone || data.phone).replace(/[^\d+]/g, '');
            window.open(`tel:${phone}`, '_self');
          } else {
            navigateTo(`/leads/${data.leadId || data.lead_id || data.entityId}`);
          }
        },
      },
      {
        id: 'view_lead',
        label: 'View Lead',
        handler: (data) => {
          navigateTo(`/leads/${data.leadId || data.lead_id || data.entityId}`);
        },
      },
    ],
  },

  TASK_DUE: {
    type: 'TASK_DUE',
    label: 'Task Due',
    description: 'Task approaching deadline',
    defaultRoute: (data) => {
      if (data.taskId || data.task_id) {
        return `/tasks?highlight=${data.taskId || data.task_id}`;
      }
      return '/tasks';
    },
    quickActions: [
      {
        id: 'complete_task',
        label: 'Complete Task',
        handler: async (data) => {
          const taskId = data.taskId || data.task_id;
          if (taskId && _apiClient) {
            try {
              await _apiClient.patch(`/api/v1/tasks/${taskId}`, { type: 'Completed' });
              await haptics.success();
            } catch (err) {
              console.error('Failed to complete task from notification:', err);
              // Fall back to navigating to the task
              navigateTo(`/tasks?highlight=${taskId}`);
            }
          } else {
            navigateTo('/tasks');
          }
        },
      },
      {
        id: 'snooze_1h',
        label: 'Snooze 1h',
        handler: async (data) => {
          const taskId = data.taskId || data.task_id;
          if (taskId && _apiClient) {
            try {
              const snoozeUntil = new Date(Date.now() + 60 * 60 * 1000).toISOString();
              await _apiClient.patch(`/api/v1/tasks/${taskId}/snooze`, { snooze_until: snoozeUntil });
              await haptics.success();
            } catch (err) {
              console.error('Failed to snooze task from notification:', err);
              navigateTo(`/tasks?highlight=${taskId}`);
            }
          } else {
            navigateTo('/tasks');
          }
        },
      },
    ],
  },

  RATE_LOCK_EXPIRING: {
    type: 'RATE_LOCK_EXPIRING',
    label: 'Rate Lock Expiring',
    description: 'Rate lock within 48 hours of expiry',
    defaultRoute: (data) => `/loans/${data.loanId || data.loan_id || data.entityId}`,
    quickActions: [
      {
        id: 'view_loan',
        label: 'View Loan',
        handler: (data) => {
          navigateTo(`/loans/${data.loanId || data.loan_id || data.entityId}`);
        },
      },
      {
        id: 'extend_lock',
        label: 'Extend Lock',
        handler: async (data) => {
          const loanId = data.loanId || data.loan_id || data.entityId;
          if (loanId && _apiClient) {
            try {
              await _apiClient.post(`/api/v1/loans/${loanId}/rate-lock/extend`);
              await haptics.success();
            } catch (err) {
              console.error('Failed to extend rate lock from notification:', err);
              // Navigate to loan detail so user can handle it manually
              navigateTo(`/loans/${loanId}`);
            }
          } else {
            navigateTo(`/loans/${loanId}`);
          }
        },
      },
    ],
  },

  DOCUMENT_NEEDED: {
    type: 'DOCUMENT_NEEDED',
    label: 'Document Needed',
    description: 'Borrower needs to upload a document',
    defaultRoute: (data) => {
      const loanId = data.loanId || data.loan_id || data.entityId;
      if (loanId) {
        return `/smart-docs/client/${loanId}`;
      }
      return '/smart-docs';
    },
    quickActions: [
      {
        id: 'send_reminder',
        label: 'Send Reminder',
        handler: async (data) => {
          const loanId = data.loanId || data.loan_id || data.entityId;
          if (loanId && _apiClient) {
            try {
              await _apiClient.post(`/api/v1/smart-docs/delivery/send-reminder`, {
                loan_id: loanId,
                document_types: data.documentTypes || data.document_types || [],
              });
              await haptics.success();
            } catch (err) {
              console.error('Failed to send document reminder from notification:', err);
              navigateTo(`/smart-docs/client/${loanId}`);
            }
          } else {
            navigateTo(loanId ? `/smart-docs/client/${loanId}` : '/smart-docs');
          }
        },
      },
      {
        id: 'view_docs',
        label: 'View Docs',
        handler: (data) => {
          const loanId = data.loanId || data.loan_id || data.entityId;
          navigateTo(loanId ? `/smart-docs/client/${loanId}` : '/smart-docs');
        },
      },
    ],
  },

  CLOSING_REMINDER: {
    type: 'CLOSING_REMINDER',
    label: 'Closing Reminder',
    description: 'Closing date approaching',
    defaultRoute: (data) => `/loans/${data.loanId || data.loan_id || data.entityId}`,
    quickActions: [],
  },

  COMPLIANCE_ALERT: {
    type: 'COMPLIANCE_ALERT',
    label: 'Compliance Alert',
    description: 'Compliance issue detected',
    defaultRoute: (data) => {
      if (data.loanId || data.loan_id) {
        return `/compliance?loan=${data.loanId || data.loan_id}`;
      }
      return '/compliance';
    },
    quickActions: [
      {
        id: 'view_alert',
        label: 'View Alert',
        handler: (data) => {
          if (data.alertId || data.alert_id) {
            navigateTo(`/compliance?alert=${data.alertId || data.alert_id}`);
          } else {
            navigateTo('/compliance');
          }
        },
      },
    ],
  },

  SYSTEM: {
    type: 'SYSTEM',
    label: 'System',
    description: 'General system notifications',
    defaultRoute: () => '/dashboard',
    quickActions: [],
  },
};

// ============================================================================
// ROUTE RESOLVER
// ============================================================================

/**
 * Get the route path for a given notification type and entity ID.
 * Useful for building links outside of the notification tap flow.
 *
 * @param {string} type - Notification category type (e.g. 'LOAN_UPDATE')
 * @param {string} [id] - Entity ID (loan, lead, task, etc.)
 * @returns {string} The route path
 */
export function getNotificationRoute(type, id) {
  const category = NOTIFICATION_CATEGORIES[type];
  if (!category) {
    return '/dashboard';
  }

  // Build a minimal data object with the entity ID
  const data = { entityId: id };
  try {
    return category.defaultRoute(data);
  } catch (err) {
    console.error(`Error resolving route for notification type "${type}":`, err);
    return '/dashboard';
  }
}

// ============================================================================
// CORE HANDLER
// ============================================================================

/**
 * Handle a notification action when the user taps a push notification.
 * Routes to the appropriate screen based on notification.data.type.
 *
 * Expects the notification object from Capacitor's pushNotificationActionPerformed,
 * which has the shape: { actionId, notification: { data, title, body, ... } }
 *
 * @param {Object} notification - The notification action event from Capacitor
 * @param {Object} notification.notification - The notification payload
 * @param {Object} notification.notification.data - Custom data attached to the push
 * @param {string} [notification.actionId] - The quick action ID if a button was tapped
 */
export async function handleNotificationAction(notification) {
  if (!_navigate) {
    console.error(
      'notificationActions: navigate function not initialized. Call initNotificationActions() first.'
    );
    return;
  }

  // Provide haptic feedback on tap
  await haptics.medium();

  // Extract data — Capacitor nests it under notification.notification.data
  const data = notification?.notification?.data || notification?.data || {};
  const type = data.type || data.category || 'SYSTEM';
  const actionId = notification?.actionId;

  const category = NOTIFICATION_CATEGORIES[type];

  if (!category) {
    console.warn(`notificationActions: unknown notification type "${type}", falling back to dashboard`);
    navigateTo('/dashboard');
    return;
  }

  // If a specific quick action button was tapped (not the default "tap" action)
  if (actionId && actionId !== 'tap') {
    const quickAction = category.quickActions.find((qa) => qa.id === actionId);
    if (quickAction) {
      try {
        await quickAction.handler(data);
      } catch (err) {
        console.error(`notificationActions: quick action "${actionId}" failed:`, err);
        // Fall back to the default route
        navigateTo(category.defaultRoute(data));
      }
      return;
    }
  }

  // Default action: navigate to the category's default route
  try {
    const route = category.defaultRoute(data);
    navigateTo(route);
  } catch (err) {
    console.error(`notificationActions: failed to resolve route for type "${type}":`, err);
    navigateTo('/dashboard');
  }
}

// ============================================================================
// INTERNAL HELPERS
// ============================================================================

/**
 * Navigate to a route with haptic confirmation.
 * Wraps the injected navigate function with safety checks.
 */
function navigateTo(path) {
  if (!path) {
    console.warn('notificationActions: navigateTo called with empty path');
    return;
  }

  if (!_navigate) {
    console.error('notificationActions: navigate function not available');
    // Last resort: use window.location for web fallback
    window.location.href = path;
    return;
  }

  try {
    _navigate(path);
  } catch (err) {
    console.error('notificationActions: navigation failed, using fallback:', err);
    window.location.href = path;
  }
}
