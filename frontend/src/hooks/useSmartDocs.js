/**
 * Smart Documents React Hook
 *
 * Custom hook for managing smart document collection state and operations.
 */

import { useState, useCallback, useEffect } from 'react';
import { smartDocsAPI } from '../services/smartDocsApi';

/**
 * Hook for managing a loan's needs list and documents
 */
export function useSmartDocs(loanId, borrowerId) {
  const [needsList, setNeedsList] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadProgress, setUploadProgress] = useState({});

  // Load needs list
  const loadNeedsList = useCallback(async () => {
    if (!loanId) return;

    try {
      setLoading(true);
      setError(null);
      const data = await smartDocsAPI.getNeedsList(loanId);
      setNeedsList(data);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load needs list:', err);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  // Load documents
  const loadDocuments = useCallback(async () => {
    if (!loanId) return;

    try {
      const data = await smartDocsAPI.getLoanDocuments(loanId);
      setDocuments(data.documents || []);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, [loanId]);

  // Initial load
  useEffect(() => {
    loadNeedsList();
    loadDocuments();
  }, [loadNeedsList, loadDocuments]);

  // Upload document
  const uploadDocument = useCallback(async (file, requestId = null, docType = null) => {
    if (!loanId || !borrowerId) {
      throw new Error('Loan ID and Borrower ID are required');
    }

    const uploadId = `${file.name}-${Date.now()}`;

    try {
      setUploadProgress(prev => ({
        ...prev,
        [uploadId]: { status: 'uploading', progress: 0, file: file.name },
      }));

      const result = await smartDocsAPI.uploadDocument(
        file,
        loanId,
        borrowerId,
        requestId,
        docType
      );

      setUploadProgress(prev => ({
        ...prev,
        [uploadId]: {
          status: result.status === 'APPROVED' ? 'success' : 'processed',
          result,
          file: file.name,
        },
      }));

      // Refresh data
      await Promise.all([loadNeedsList(), loadDocuments()]);

      return result;
    } catch (err) {
      setUploadProgress(prev => ({
        ...prev,
        [uploadId]: { status: 'error', error: err.message, file: file.name },
      }));
      throw err;
    }
  }, [loanId, borrowerId, loadNeedsList, loadDocuments]);

  // Generate needs list
  const generateNeedsList = useCallback(async (params) => {
    try {
      setLoading(true);
      setError(null);
      const result = await smartDocsAPI.generateNeedsList({
        loan_id: loanId,
        borrower_id: borrowerId,
        ...params,
      });
      setNeedsList(result);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [loanId, borrowerId]);

  // Waive request
  const waiveRequest = useCallback(async (requestId, reason, waivedBy) => {
    try {
      await smartDocsAPI.waiveRequest(requestId, reason, waivedBy);
      await loadNeedsList();
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }, [loadNeedsList]);

  // Manual review
  const submitReview = useCallback(async (documentId, decision, reviewer, notes) => {
    try {
      await smartDocsAPI.manualReview(documentId, decision, reviewer, notes);
      await Promise.all([loadNeedsList(), loadDocuments()]);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }, [loadNeedsList, loadDocuments]);

  // Clear upload progress
  const clearUploadProgress = useCallback((uploadId = null) => {
    if (uploadId) {
      setUploadProgress(prev => {
        const next = { ...prev };
        delete next[uploadId];
        return next;
      });
    } else {
      setUploadProgress({});
    }
  }, []);

  // Compute statistics
  const stats = needsList ? {
    totalRequests: needsList.total_requests || 0,
    openCount: needsList.open_count || 0,
    pendingReviewCount: needsList.pending_review_count || 0,
    acceptedCount: needsList.accepted_count || 0,
    completionPercentage: needsList.total_requests > 0
      ? Math.round((needsList.accepted_count / needsList.total_requests) * 100)
      : 0,
  } : null;

  return {
    // State
    needsList,
    documents,
    loading,
    error,
    uploadProgress,
    stats,

    // Actions
    loadNeedsList,
    loadDocuments,
    uploadDocument,
    generateNeedsList,
    waiveRequest,
    submitReview,
    clearUploadProgress,
    refresh: useCallback(() => {
      loadNeedsList();
      loadDocuments();
    }, [loadNeedsList, loadDocuments]),
  };
}

/**
 * Hook for document freshness management
 */
export function useDocumentFreshness(loanId = null) {
  const [expiringDocs, setExpiringDocs] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadExpiring = useCallback(async (daysAhead = 14) => {
    try {
      setLoading(true);
      const data = await smartDocsAPI.getExpiringDocuments(loanId, daysAhead);
      setExpiringDocs(data.expiring_documents || []);
    } catch (err) {
      console.error('Failed to load expiring documents:', err);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    loadExpiring();
  }, [loadExpiring]);

  return {
    expiringDocs,
    loading,
    refresh: loadExpiring,
  };
}

/**
 * Hook for payroll frequency inference
 */
export function usePayrollFrequency(borrowerId) {
  const [frequency, setFrequency] = useState(null);
  const [loading, setLoading] = useState(false);

  const infer = useCallback(async () => {
    if (!borrowerId) return;

    try {
      setLoading(true);
      const result = await smartDocsAPI.inferPayrollFrequency(borrowerId);
      if (result.inferred) {
        setFrequency(result.inferred_frequency);
      }
      return result;
    } catch (err) {
      console.error('Failed to infer payroll frequency:', err);
    } finally {
      setLoading(false);
    }
  }, [borrowerId]);

  return {
    frequency,
    loading,
    infer,
  };
}

export default useSmartDocs;
