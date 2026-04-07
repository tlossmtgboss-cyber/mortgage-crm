/**
 * Siri Shortcuts Service
 * Perennia AI - Donate user activities to Siri for shortcut suggestions
 *
 * When the user performs key actions (viewing the pipeline, contacting a
 * client, managing tasks), this service donates an NSUserActivity to Siri.
 * iOS learns the user's patterns and surfaces these as suggested shortcuts
 * on the lock screen, in Spotlight, and via "Hey Siri" voice invocation.
 *
 * Usage:
 *   import { donateViewPipeline, donateContactClient } from './siriShortcuts';
 *
 *   // When user views their pipeline
 *   donateViewPipeline();
 *
 *   // When user contacts a specific client
 *   donateContactClient('Jane Smith', '/leads/42');
 *
 *   // React hook for shortcut activation events
 *   const { lastActivation } = useSiriShortcuts();
 */

import { useState, useEffect, useCallback } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';

// ---------------------------------------------------------------------------
// Native plugin bridge
// ---------------------------------------------------------------------------

const SiriShortcuts = registerPlugin('SiriShortcuts');

// ---------------------------------------------------------------------------
// Activity type constants (must match Info.plist NSUserActivityTypes)
// ---------------------------------------------------------------------------

const ACTIVITY_TYPES = {
  VIEW_PROPERTY: 'com.perenniaai.crm.viewProperty',
  CONTACT_CLIENT: 'com.perenniaai.crm.contactClient',
  MANAGE_TASK: 'com.perenniaai.crm.manageTask',
};

// ---------------------------------------------------------------------------
// Guard: only run on native platforms
// ---------------------------------------------------------------------------

function isNative() {
  return Capacitor.isNativePlatform();
}

// ---------------------------------------------------------------------------
// Core donation function
// ---------------------------------------------------------------------------

/**
 * Donate a user activity to Siri. No-ops on web.
 *
 * @param {Object} options
 * @param {string} options.type - Activity type from ACTIVITY_TYPES
 * @param {string} options.title - Shortcut title shown to the user
 * @param {string} [options.description] - Optional subtitle
 * @param {string} [options.route] - Web app route to navigate to on invocation
 * @param {Object} [options.userInfo] - Arbitrary key-value pairs
 * @returns {Promise<{donated: boolean}>}
 */
async function donateActivity({ type, title, description, route, userInfo }) {
  if (!isNative()) {
    return { donated: false };
  }

  try {
    const result = await SiriShortcuts.donateActivity({
      type,
      title,
      description: description || '',
      route: route || undefined,
      userInfo: userInfo || {},
    });
    return result;
  } catch (error) {
    console.warn('[SiriShortcuts] Donation failed:', error.message);
    return { donated: false };
  }
}

// ---------------------------------------------------------------------------
// Convenience donation functions
// ---------------------------------------------------------------------------

/**
 * Donate a "View Pipeline" shortcut.
 * Call this when the user navigates to the leads/pipeline page.
 */
export async function donateViewPipeline() {
  return donateActivity({
    type: ACTIVITY_TYPES.VIEW_PROPERTY,
    title: 'View Pipeline',
    description: 'Check your mortgage pipeline status',
    route: '/leads',
  });
}

/**
 * Donate a "View Lead" shortcut for a specific lead.
 * Call this when the user opens a lead detail page.
 *
 * @param {string} leadName - Display name of the lead
 * @param {string|number} leadId - Lead ID for routing
 */
export async function donateViewLead(leadName, leadId) {
  return donateActivity({
    type: ACTIVITY_TYPES.VIEW_PROPERTY,
    title: `View ${leadName}`,
    description: `Open ${leadName}'s loan file`,
    route: `/leads/${leadId}`,
    userInfo: { leadId: String(leadId), leadName },
  });
}

/**
 * Donate a "Contact Client" shortcut.
 * Call this when the user contacts (calls, emails, SMS) a client.
 *
 * @param {string} clientName - Display name of the client
 * @param {string} [route] - Optional route override (defaults to /leads)
 * @param {string|number} [leadId] - Optional lead ID
 */
export async function donateContactClient(clientName, route, leadId) {
  return donateActivity({
    type: ACTIVITY_TYPES.CONTACT_CLIENT,
    title: `Contact ${clientName}`,
    description: `Reach out to ${clientName}`,
    route: route || '/leads',
    userInfo: {
      clientName,
      ...(leadId ? { leadId: String(leadId) } : {}),
    },
  });
}

/**
 * Donate a "Manage Tasks" shortcut.
 * Call this when the user navigates to or interacts with their task list.
 */
export async function donateManageTasks() {
  return donateActivity({
    type: ACTIVITY_TYPES.MANAGE_TASK,
    title: 'Manage Tasks',
    description: 'View and manage your tasks',
    route: '/tasks',
  });
}

/**
 * Donate a "Complete Task" shortcut for a specific task.
 * Call this when the user completes or interacts with a specific task.
 *
 * @param {string} taskTitle - Title of the task
 * @param {string|number} taskId - Task ID
 */
export async function donateCompleteTask(taskTitle, taskId) {
  return donateActivity({
    type: ACTIVITY_TYPES.MANAGE_TASK,
    title: `Task: ${taskTitle}`,
    description: `Manage task: ${taskTitle}`,
    route: '/tasks',
    userInfo: { taskId: String(taskId), taskTitle },
  });
}

// ---------------------------------------------------------------------------
// Clear all donations
// ---------------------------------------------------------------------------

/**
 * Clear all donated Siri shortcut activities.
 * Call this on logout or when the user wants to reset suggestions.
 *
 * @returns {Promise<{cleared: boolean}>}
 */
export async function clearDonations() {
  if (!isNative()) {
    return { cleared: false };
  }

  try {
    const result = await SiriShortcuts.clearDonations();
    return result;
  } catch (error) {
    console.warn('[SiriShortcuts] Clear failed:', error.message);
    return { cleared: false };
  }
}

// ---------------------------------------------------------------------------
// Get suggested shortcuts
// ---------------------------------------------------------------------------

/**
 * Retrieve suggested shortcuts based on usage patterns.
 * Use this to display a list of shortcuts the user can add to Siri.
 *
 * @returns {Promise<Array<{type: string, title: string, description: string, route: string, frequency: number, isPersonalized: boolean}>>}
 */
export async function getSuggestedActions() {
  if (!isNative()) {
    return [];
  }

  try {
    const result = await SiriShortcuts.getSuggestedActions();
    return result.suggestions || [];
  } catch (error) {
    console.warn('[SiriShortcuts] getSuggestedActions failed:', error.message);
    return [];
  }
}

// ---------------------------------------------------------------------------
// React Hook
// ---------------------------------------------------------------------------

/**
 * React hook for Siri Shortcuts integration.
 *
 * Listens for shortcut activation events (when the user invokes a shortcut
 * via Siri or Spotlight) and provides the last activation data.
 *
 * Also exposes suggestion data and helper methods.
 *
 * @returns {{
 *   lastActivation: { type: string, title: string, route: string, userInfo: Object } | null,
 *   suggestions: Array,
 *   isNative: boolean,
 *   refreshSuggestions: () => Promise<void>,
 *   clearAll: () => Promise<void>,
 * }}
 */
export function useSiriShortcuts() {
  const [lastActivation, setLastActivation] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const native = isNative();

  // Listen for shortcut activation events from the native layer
  useEffect(() => {
    if (!native) return;

    let listener = null;

    const setup = async () => {
      try {
        listener = await SiriShortcuts.addListener('shortcutActivated', (data) => {
          setLastActivation({
            type: data.type,
            title: data.title,
            route: data.route,
            userInfo: data.userInfo || {},
            timestamp: new Date().toISOString(),
          });
        });
      } catch (error) {
        console.warn('[SiriShortcuts] Failed to add listener:', error.message);
      }
    };

    setup();

    return () => {
      if (listener && typeof listener.remove === 'function') {
        listener.remove();
      }
    };
  }, [native]);

  const refreshSuggestions = useCallback(async () => {
    const result = await getSuggestedActions();
    setSuggestions(result);
  }, []);

  // Load suggestions on mount
  useEffect(() => {
    if (native) {
      refreshSuggestions();
    }
  }, [native, refreshSuggestions]);

  const clearAll = useCallback(async () => {
    await clearDonations();
    setSuggestions([]);
    setLastActivation(null);
  }, []);

  return {
    lastActivation,
    suggestions,
    isNative: native,
    refreshSuggestions,
    clearAll,
  };
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export { ACTIVITY_TYPES };

export default {
  donateViewPipeline,
  donateViewLead,
  donateContactClient,
  donateManageTasks,
  donateCompleteTask,
  clearDonations,
  getSuggestedActions,
  useSiriShortcuts,
  ACTIVITY_TYPES,
};
