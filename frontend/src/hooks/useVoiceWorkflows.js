import { useState, useCallback } from 'react';
import { getItem, STORAGE_KEYS } from '../utils/storage';
import { toast } from '../utils/toast';
import { haptics } from '../services/nativeServices';

/**
 * Custom hook for tracking and managing voice-initiated workflows.
 *
 * @param {Object} options
 * @param {string} options.apiBaseUrl - Base URL for REST API calls
 */
const useVoiceWorkflows = ({ apiBaseUrl }) => {
  const [activeWorkflows, setActiveWorkflows] = useState([]);

  // Cancel an active workflow
  const cancelWorkflow = useCallback(
    async (workflowId) => {
      try {
        const token = await getItem(STORAGE_KEYS.TOKEN);
        const response = await fetch(
          `${apiBaseUrl}/api/v1/voice-workflows/${workflowId}/cancel`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          },
        );
        if (response.ok) {
          setActiveWorkflows((prev) =>
            prev.map((w) =>
              w.workflow_id === workflowId ? { ...w, state: 'cancelled' } : w,
            ),
          );
        }
      } catch (err) {
        console.error('Failed to cancel workflow:', err);
      }
    },
    [apiBaseUrl],
  );

  // Handle a workflow_status message from WebSocket
  const updateWorkflowStatus = useCallback((data) => {
    setActiveWorkflows((prev) => {
      const idx = prev.findIndex((w) => w.workflow_id === data.workflow_id);
      if (idx >= 0) {
        const updated = [...prev];
        updated[idx] = { ...updated[idx], ...data };
        return updated;
      }
      return [...prev, data];
    });

    // Celebration toast when appointment is booked
    if (data.state === 'appointment_booked') {
      toast.success(
        `Meeting with ${data.contact_name || 'contact'} booked!`,
      );
      haptics.success();
    } else if (data.state === 'failed') {
      toast.error(
        `Scheduling with ${data.contact_name || 'contact'} failed`,
      );
    }
  }, []);

  return {
    activeWorkflows,
    cancelWorkflow,
    updateWorkflowStatus,
  };
};

export default useVoiceWorkflows;
