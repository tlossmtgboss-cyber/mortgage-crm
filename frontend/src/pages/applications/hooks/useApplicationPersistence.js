/**
 * useApplicationPersistence Hook
 * Handles auto-save to localStorage and API with debouncing
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { useApplication } from '../contexts/ApplicationContext';

const DEFAULT_DEBOUNCE_MS = 2000;
const STORAGE_KEY_PREFIX = 'mortgage_application_';

/**
 * Get storage key for an application
 */
function getStorageKey(applicationType, workspaceSlug) {
  const suffix = workspaceSlug || 'draft';
  return `${STORAGE_KEY_PREFIX}${applicationType}_${suffix}`;
}

/**
 * Main persistence hook
 */
export function useApplicationPersistence(options = {}) {
  const {
    debounceMs = DEFAULT_DEBOUNCE_MS,
    enableLocalStorage = true,
    enableApiSave = true,
    apiEndpoint = null,
    onSaveStart = () => {},
    onSaveSuccess = () => {},
    onSaveError = () => {},
    onRestoreSuccess = () => {},
  } = options;

  const { state, actions } = useApplication();
  const { formData, currentStage, currentQuestionIndex, applicationType, workspaceSlug, isDirty } = state;

  const [isSaving, setIsSaving] = useState(false);
  const [lastError, setLastError] = useState(null);
  const [showRestorePrompt, setShowRestorePrompt] = useState(false);
  const [pendingRestoreData, setPendingRestoreData] = useState(null);
  const debounceTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  // Storage key
  const storageKey = getStorageKey(applicationType, workspaceSlug);

  /**
   * Strip SSN from form data (used for both localStorage and API draft saves)
   */
  const sanitizeFormData = useCallback((data) => {
    if (!data) return data;

    let sanitized = data;

    // Strip SSN from borrowers array
    if (data.borrowers && Array.isArray(data.borrowers)) {
      sanitized = {
        ...data,
        borrowers: data.borrowers.map(borrower => {
          if (!borrower) return borrower;
          const { ssn, ...rest } = borrower;
          return rest;
        }),
      };
    }

    // Strip top-level SSN if present
    if (sanitized.ssn !== undefined) {
      const { ssn, ...rest } = sanitized;
      sanitized = rest;
    }

    return sanitized;
  }, []);

  /**
   * Save to localStorage
   */
  const saveToLocalStorage = useCallback(() => {
    if (!enableLocalStorage) return;

    try {
      const sanitizedFormData = sanitizeFormData(formData);

      const dataToSave = {
        formData: sanitizedFormData,
        currentStage,
        currentQuestionIndex,
        applicationType,
        savedAt: new Date().toISOString(),
        version: 1,
      };

      localStorage.setItem(storageKey, JSON.stringify(dataToSave));
      return true;
    } catch (error) {
      console.warn('Failed to save to localStorage:', error);
      return false;
    }
  }, [formData, currentStage, currentQuestionIndex, applicationType, storageKey, enableLocalStorage, sanitizeFormData]);

  /**
   * Save to API (SSN stripped — only sent on final submission, not draft saves)
   */
  const saveToApi = useCallback(async () => {
    if (!enableApiSave || !apiEndpoint) return true;

    try {
      const token = localStorage.getItem('token');
      const sanitizedFormData = sanitizeFormData(formData);

      const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        body: JSON.stringify({
          data: sanitizedFormData,
          currentStage,
          applicationType,
        }),
      });

      if (!response.ok) {
        throw new Error(`API save failed: ${response.status}`);
      }

      return true;
    } catch (error) {
      console.error('Failed to save to API:', error);
      throw error;
    }
  }, [formData, currentStage, applicationType, apiEndpoint, enableApiSave, sanitizeFormData]);

  /**
   * Perform save operation
   */
  const performSave = useCallback(async () => {
    if (!isMountedRef.current) return;

    setIsSaving(true);
    setLastError(null);
    onSaveStart();

    try {
      // Save to localStorage first (fast, synchronous)
      const localSaveSuccess = saveToLocalStorage();

      // Then save to API (async)
      if (enableApiSave && apiEndpoint) {
        await saveToApi();
      }

      if (isMountedRef.current) {
        setIsSaving(false);
        actions.setLastSaved(new Date().toISOString());
        onSaveSuccess();
      }
    } catch (error) {
      if (isMountedRef.current) {
        setIsSaving(false);
        setLastError(error.message);
        onSaveError(error);
      }
    }
  }, [saveToLocalStorage, saveToApi, enableApiSave, apiEndpoint, actions, onSaveStart, onSaveSuccess, onSaveError]);

  /**
   * Debounced save - called on form data changes
   */
  const debouncedSave = useCallback(() => {
    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set new timer
    debounceTimerRef.current = setTimeout(() => {
      performSave();
    }, debounceMs);
  }, [performSave, debounceMs]);

  /**
   * Force immediate save (bypass debounce)
   */
  const forceSave = useCallback(async () => {
    // Clear any pending debounced save
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    await performSave();
  }, [performSave]);

  /**
   * Restore from localStorage
   */
  const restoreFromLocalStorage = useCallback(() => {
    if (!enableLocalStorage) return null;

    try {
      const savedData = localStorage.getItem(storageKey);
      if (!savedData) return null;

      const parsed = JSON.parse(savedData);

      // Validate saved data structure
      if (!parsed.formData || !parsed.applicationType) {
        console.warn('Invalid saved data structure');
        return null;
      }

      return parsed;
    } catch (error) {
      console.warn('Failed to restore from localStorage:', error);
      return null;
    }
  }, [storageKey, enableLocalStorage]);

  /**
   * Clear saved data
   */
  const clearSavedData = useCallback(() => {
    try {
      localStorage.removeItem(storageKey);
      return true;
    } catch (error) {
      console.warn('Failed to clear saved data:', error);
      return false;
    }
  }, [storageKey]);

  /**
   * Handle restore confirmation
   */
  const confirmRestore = useCallback(() => {
    if (pendingRestoreData) {
      actions.restoreState({
        formData: pendingRestoreData.formData,
        currentStage: pendingRestoreData.currentStage,
        currentQuestionIndex: pendingRestoreData.currentQuestionIndex || 0,
      });
      onRestoreSuccess(pendingRestoreData);
    }
    setShowRestorePrompt(false);
    setPendingRestoreData(null);
  }, [pendingRestoreData, actions, onRestoreSuccess]);

  const declineRestore = useCallback(() => {
    clearSavedData();
    setShowRestorePrompt(false);
    setPendingRestoreData(null);
  }, [clearSavedData]);

  /**
   * Auto-restore on mount
   */
  useEffect(() => {
    const savedData = restoreFromLocalStorage();

    if (savedData) {
      // Show inline restore prompt instead of window.confirm
      setPendingRestoreData(savedData);
      setShowRestorePrompt(true);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Auto-save on form data changes (debounced)
   */
  useEffect(() => {
    if (isDirty) {
      debouncedSave();
    }

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [formData, isDirty, debouncedSave]);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  /**
   * Save before page unload
   */
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isDirty) {
        // Save synchronously before leaving
        saveToLocalStorage();

        // Show browser's default "unsaved changes" dialog
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty, saveToLocalStorage]);

  return {
    // State
    isSaving,
    lastError,
    lastSavedAt: state.lastSavedAt,
    isDirty,
    showRestorePrompt,

    // Actions
    forceSave,
    clearSavedData,
    restoreFromLocalStorage,
    confirmRestore,
    declineRestore,

    // Utility
    storageKey,
  };
}

/**
 * Simplified hook for just localStorage persistence (no API)
 */
export function useLocalStoragePersistence(applicationType, options = {}) {
  return useApplicationPersistence({
    ...options,
    enableApiSave: false,
  });
}

export default useApplicationPersistence;
