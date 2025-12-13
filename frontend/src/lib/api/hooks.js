/**
 * React Hooks for Perennia API
 *
 * Custom hooks for easy data fetching and mutations with the Perennia API.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { api, PerenniaAPIError } from './client';

/**
 * Generic data fetching hook
 * @param {Function} fetchFn - Async function that returns data
 * @param {Array} deps - Dependencies array for re-fetching
 * @param {Object} options - Options
 */
export function useApiQuery(fetchFn, deps = [], options = {}) {
  const { enabled = true, onSuccess, onError, initialData = null } = options;

  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!enabled) return;

    setLoading(true);
    setError(null);

    try {
      const result = await fetchFn();
      setData(result);
      if (onSuccess) onSuccess(result);
    } catch (err) {
      setError(err);
      if (onError) onError(err);
    } finally {
      setLoading(false);
    }
  }, [fetchFn, enabled, onSuccess, onError]);

  useEffect(() => {
    fetchData();
  }, [...deps, enabled]);

  return { data, loading, error, refetch: fetchData };
}

/**
 * Generic mutation hook
 * @param {Function} mutationFn - Async function that performs mutation
 * @param {Object} options - Options
 */
export function useApiMutation(mutationFn, options = {}) {
  const { onSuccess, onError, onSettled } = options;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const mutate = useCallback(async (...args) => {
    setLoading(true);
    setError(null);

    try {
      const result = await mutationFn(...args);
      setData(result);
      if (onSuccess) onSuccess(result);
      return result;
    } catch (err) {
      setError(err);
      if (onError) onError(err);
      throw err;
    } finally {
      setLoading(false);
      if (onSettled) onSettled();
    }
  }, [mutationFn, onSuccess, onError, onSettled]);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { mutate, loading, error, data, reset };
}

// =============================================================================
// WORKSPACE HOOKS
// =============================================================================

/**
 * Hook to fetch workspace document status
 * @param {number} workspaceId
 */
export function useWorkspaceDocumentStatus(workspaceId) {
  return useApiQuery(
    () => api.getWorkspaceDocumentStatus(workspaceId),
    [workspaceId],
    { enabled: !!workspaceId }
  );
}

/**
 * Hook to fetch workspace milestones
 * @param {number} workspaceId
 */
export function useWorkspaceMilestones(workspaceId) {
  return useApiQuery(
    () => api.getWorkspaceMilestones(workspaceId),
    [workspaceId],
    { enabled: !!workspaceId }
  );
}

/**
 * Hook to fetch workspace activity feed
 * @param {number} workspaceId
 * @param {Object} options
 */
export function useWorkspaceActivityFeed(workspaceId, { limit = 50 } = {}) {
  return useApiQuery(
    () => api.getWorkspaceActivityFeed(workspaceId, { limit }),
    [workspaceId, limit],
    { enabled: !!workspaceId }
  );
}

/**
 * Hook to fetch workspace notifications
 * @param {number} workspaceId
 * @param {Object} options
 */
export function useWorkspaceNotifications(workspaceId, { unreadOnly = false } = {}) {
  return useApiQuery(
    () => api.getWorkspaceNotifications(workspaceId, { unreadOnly }),
    [workspaceId, unreadOnly],
    { enabled: !!workspaceId }
  );
}

/**
 * Hook to fetch workspace documents
 * @param {number} workspaceId
 * @param {Object} filters
 */
export function useWorkspaceDocuments(workspaceId, { status, docType } = {}) {
  return useApiQuery(
    () => api.listWorkspaceDocuments(workspaceId, { status, docType }),
    [workspaceId, status, docType],
    { enabled: !!workspaceId }
  );
}

// =============================================================================
// AI ASSISTANT HOOKS
// =============================================================================

/**
 * Hook for AI assistant chat
 * @param {number} workspaceId
 */
export function useAIAssistant(workspaceId) {
  const [messages, setMessages] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = useCallback(async (content) => {
    if (!content.trim() || loading) return;

    // Add user message
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setLoading(true);
    setError(null);

    try {
      const response = await api.chatWithAssistant({
        workspaceId,
        message: content,
        conversationHistory: messages.slice(-10),
      });

      // Add assistant message
      const assistantMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: new Date().toISOString(),
        actions: response.actions,
      };
      setMessages(prev => [...prev, assistantMessage]);
      setSuggestions(response.suggestions || []);

      return response;
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [workspaceId, messages, loading]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSuggestions([]);
    setError(null);
  }, []);

  return {
    messages,
    suggestions,
    loading,
    error,
    sendMessage,
    clearMessages,
  };
}

/**
 * Hook to fetch quick actions
 * @param {number} workspaceId
 */
export function useQuickActions(workspaceId) {
  return useApiQuery(
    () => api.getQuickActions(workspaceId),
    [workspaceId],
    { enabled: !!workspaceId }
  );
}

/**
 * Hook to fetch FAQ
 */
export function useFAQ() {
  return useApiQuery(() => api.getFAQ(), []);
}

/**
 * Hook to fetch contextual tips
 * @param {number} workspaceId
 */
export function useTips(workspaceId) {
  return useApiQuery(
    () => api.getTips(workspaceId),
    [workspaceId],
    { enabled: !!workspaceId }
  );
}

// =============================================================================
// DOCUMENT UPLOAD HOOKS
// =============================================================================

/**
 * Hook for document upload with progress tracking
 * @param {number} workspaceId
 */
export function useDocumentUpload(workspaceId) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [uploadedDocument, setUploadedDocument] = useState(null);
  const abortControllerRef = useRef(null);

  const upload = useCallback(async (file, { requestId, documentType, documentSubtype } = {}) => {
    setUploading(true);
    setProgress(0);
    setError(null);
    setUploadedDocument(null);

    try {
      // Step 1: Get presigned URL
      setProgress(10);
      const initResponse = await api.initiateDocumentUpload({
        workspaceId,
        requestId,
        fileName: file.name,
        fileSize: file.size,
        mimeType: file.type,
        documentType,
        documentSubtype,
      });

      // Step 2: Upload to S3
      setProgress(20);
      abortControllerRef.current = new AbortController();

      const uploadResponse = await fetch(initResponse.upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': file.type,
        },
        signal: abortControllerRef.current.signal,
      });

      if (!uploadResponse.ok) {
        throw new Error('Upload to storage failed');
      }

      setProgress(80);

      // Step 3: Confirm upload
      const confirmResponse = await api.confirmDocumentUpload({
        workspaceId,
        documentId: initResponse.document_id,
        etag: uploadResponse.headers.get('ETag'),
      });

      setProgress(100);
      setUploadedDocument({
        id: initResponse.document_id,
        fileName: file.name,
        ...confirmResponse,
      });

      return confirmResponse;
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err);
      }
      throw err;
    } finally {
      setUploading(false);
      abortControllerRef.current = null;
    }
  }, [workspaceId]);

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  const reset = useCallback(() => {
    setUploading(false);
    setProgress(0);
    setError(null);
    setUploadedDocument(null);
  }, []);

  return {
    upload,
    cancel,
    reset,
    uploading,
    progress,
    error,
    uploadedDocument,
  };
}

// =============================================================================
// AUTHENTICATION HOOKS
// =============================================================================

/**
 * Hook for portal session management
 */
export function usePortalSession() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const checkSession = useCallback(async () => {
    setLoading(true);
    try {
      const sessionInfo = await api.getSessionInfo();
      setSession(sessionInfo.valid ? sessionInfo : null);
    } catch (err) {
      setSession(null);
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
      setSession(null);
    } catch (err) {
      setError(err);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const result = await api.refreshSession();
      if (result.success) {
        await checkSession();
      }
      return result;
    } catch (err) {
      setError(err);
      throw err;
    }
  }, [checkSession]);

  return {
    session,
    loading,
    error,
    isAuthenticated: !!session?.valid,
    logout,
    refresh,
    checkSession,
  };
}

/**
 * Hook for sending magic links
 */
export function useSendMagicLink() {
  return useApiMutation(
    ({ workspaceId, email, redirectPath }) =>
      api.sendMagicLink({ workspaceId, email, redirectPath })
  );
}

/**
 * Hook for verifying magic links
 */
export function useVerifyMagicLink() {
  return useApiMutation((token) => api.verifyMagicLink(token));
}

// =============================================================================
// MUTATION HOOKS
// =============================================================================

/**
 * Hook for marking notifications as read
 * @param {number} workspaceId
 */
export function useMarkNotificationRead(workspaceId) {
  return useApiMutation((notificationId) =>
    api.markNotificationRead(workspaceId, notificationId)
  );
}

/**
 * Hook for marking all notifications as read
 * @param {number} workspaceId
 */
export function useMarkAllNotificationsRead(workspaceId) {
  return useApiMutation(() => api.markAllNotificationsRead(workspaceId));
}

/**
 * Hook for updating milestone
 * @param {number} workspaceId
 */
export function useUpdateMilestone(workspaceId) {
  return useApiMutation(({ milestoneId, status, notes, autoNotify }) =>
    api.updateMilestone(workspaceId, milestoneId, { status, notes, autoNotify })
  );
}

/**
 * Hook for reviewing documents
 */
export function useReviewDocument() {
  return useApiMutation(({ documentId, action, rejectionReason, notes, notifyBorrower }) =>
    api.reviewDocument(documentId, { action, rejectionReason, notes, notifyBorrower })
  );
}

/**
 * Hook for submitting AI assistant feedback
 */
export function useAssistantFeedback() {
  return useApiMutation(({ workspaceId, messageId, rating, feedback }) =>
    api.submitAssistantFeedback({ workspaceId, messageId, rating, feedback })
  );
}

// =============================================================================
// WORKSPACE DATA HOOKS
// =============================================================================

/**
 * Hook to fetch full workspace data (PURL endpoint)
 * @param {string} slug
 */
export function useWorkspaceData(slug) {
  return useApiQuery(
    () => api.getWorkspaceData(slug),
    [slug],
    { enabled: !!slug }
  );
}

/**
 * Hook for application management
 * @param {string} slug
 */
export function useWorkspaceApplication(slug) {
  const { data, loading, error, refetch } = useApiQuery(
    () => api.getWorkspaceApplication(slug),
    [slug],
    { enabled: !!slug }
  );

  const saveMutation = useApiMutation(
    (applicationData) => api.saveApplication(slug, applicationData)
  );

  const submitMutation = useApiMutation(() => api.submitApplication(slug));

  return {
    application: data?.application,
    loading,
    error,
    refetch,
    save: saveMutation.mutate,
    saving: saveMutation.loading,
    saveError: saveMutation.error,
    submit: submitMutation.mutate,
    submitting: submitMutation.loading,
    submitError: submitMutation.error,
  };
}

/**
 * Hook for sending messages
 * @param {string} slug
 */
export function useSendMessage(slug) {
  return useApiMutation(({ content, messageType = 'text' }) =>
    api.sendMessage(slug, { content, messageType })
  );
}
