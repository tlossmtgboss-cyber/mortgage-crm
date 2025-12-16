/**
 * Task Events - Cross-component task synchronization
 *
 * This module provides a simple event-based system for synchronizing
 * task state across different components (Tasks page, ActionSidebar, etc.)
 */

// Event names
export const TASK_EVENTS = {
  TASK_COMPLETED: 'task:completed',
  TASK_CREATED: 'task:created',
  TASK_UPDATED: 'task:updated',
  TASK_DELETED: 'task:deleted',
  TASKS_REFRESH: 'tasks:refresh'
};

/**
 * Emit a task event
 * @param {string} eventName - One of TASK_EVENTS
 * @param {object} data - Event data (taskId, etc.)
 */
export const emitTaskEvent = (eventName, data = {}) => {
  const event = new CustomEvent(eventName, {
    detail: {
      ...data,
      timestamp: Date.now()
    }
  });
  window.dispatchEvent(event);
  console.log(`[TaskEvents] Emitted: ${eventName}`, data);
};

/**
 * Subscribe to a task event
 * @param {string} eventName - One of TASK_EVENTS
 * @param {function} callback - Handler function receiving event detail
 * @returns {function} Unsubscribe function
 */
export const subscribeToTaskEvent = (eventName, callback) => {
  const handler = (event) => {
    callback(event.detail);
  };
  window.addEventListener(eventName, handler);
  return () => window.removeEventListener(eventName, handler);
};

/**
 * Emit task completed event
 * @param {string|number} taskId - The completed task ID
 * @param {string} source - Where the completion originated ('tasks', 'action-sidebar', etc.)
 */
export const emitTaskCompleted = (taskId, source = 'unknown') => {
  emitTaskEvent(TASK_EVENTS.TASK_COMPLETED, { taskId, source });
};

/**
 * Request all task views to refresh their data
 * @param {string} source - Where the refresh request originated
 */
export const requestTasksRefresh = (source = 'unknown') => {
  emitTaskEvent(TASK_EVENTS.TASKS_REFRESH, { source });
};
