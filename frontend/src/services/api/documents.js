/**
 * Document management API calls — Document Drop, Email Drop, Perennia Docs.
 */
import api, { ensureArray } from './client.js';

// Email Drop API (drag-and-drop email/document processing)
export const emailDropAPI = {
  // Parse email with AI to extract fields and suggest actions
  parse: async (emailData) => {
    const response = await api.post('/api/v1/email-drop/parse', {
      email_data: {
        filename: emailData.filename,
        from: emailData.from,
        to: emailData.to,
        subject: emailData.subject,
        date: emailData.date,
        body: emailData.body,
        raw_content: emailData.rawContent,
        matched_borrower: emailData.matchedBorrower,
        matched_loan_number: emailData.matchedLoanNumber,
        confidence: emailData.confidence
      },
      parse_mode: 'smart'
    });
    return response.data;
  },

  // Process email based on user's chosen action
  process: async (action, emailData, extractedFields, targetEntityId, targetEntityType, createNew, userAnswers) => {
    const response = await api.post('/api/v1/email-drop/process', {
      action,
      email_data: {
        filename: emailData.filename,
        from: emailData.from,
        to: emailData.to,
        subject: emailData.subject,
        date: emailData.date,
        body: emailData.body,
        raw_content: emailData.rawContent,
        matched_borrower: emailData.matchedBorrower,
        matched_loan_number: emailData.matchedLoanNumber,
        confidence: emailData.confidence
      },
      extracted_fields: extractedFields || {},
      target_entity_id: targetEntityId,
      target_entity_type: targetEntityType,
      create_new: createNew || false,
      user_answers: userAnswers || {}
    });
    return response.data;
  },

  // Search for matching leads/loans
  searchMatches: async (searchTerm, email, loanNumber) => {
    const response = await api.post('/api/v1/email-drop/search-matches', {
      search_term: searchTerm,
      email: email,
      loan_number: loanNumber
    });
    return response.data;
  },

  // Health check
  health: async () => {
    const response = await api.get('/api/v1/email-drop/health');
    return response.data;
  }
};

// Document Drop API (drag-and-drop document upload)
export const documentDropAPI = {
  // Upload a document file
  upload: async (file, borrowerId, loanId, docType) => {
    const formData = new FormData();
    formData.append('file', file);
    if (borrowerId) formData.append('borrower_id', borrowerId);
    if (loanId) formData.append('loan_id', loanId);
    if (docType) formData.append('doc_type', docType);

    const response = await api.post('/api/v1/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Classify a document with AI
  classify: async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/api/v1/documents/classify', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Get documents for a borrower or loan
  getDocuments: async (borrowerId, loanId) => {
    const params = {};
    if (borrowerId) params.borrower_id = borrowerId;
    if (loanId) params.loan_id = loanId;

    const response = await api.get('/api/v1/documents/', { params });
    return ensureArray(response.data, 'documents');
  }
};

// Perennia Docs API
export const perenniaDocsAPI = {
  // Template Packs
  getTemplatePacks: async () => {
    const response = await api.get('/api/v1/perennia-docs/template-packs');
    return response.data;
  },

  getTemplatePack: async (packId) => {
    const response = await api.get(`/api/v1/perennia-docs/template-packs/${packId}`);
    return response.data;
  },

  createTemplatePack: async (data) => {
    const response = await api.post('/api/v1/perennia-docs/template-packs', data);
    return response.data;
  },

  updateTemplatePack: async (packId, data) => {
    const response = await api.put(`/api/v1/perennia-docs/template-packs/${packId}`, data);
    return response.data;
  },

  deleteTemplatePack: async (packId) => {
    await api.delete(`/api/v1/perennia-docs/template-packs/${packId}`);
  },

  // Document Review Queue
  getReviewQueue: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/review-queue', { params });
    return response.data;
  },

  approveDocuments: async (documentIds) => {
    const response = await api.post('/api/v1/perennia-docs/review/approve', {
      document_ids: documentIds,
    });
    return response.data;
  },

  rejectDocuments: async (documentIds, reason) => {
    const response = await api.post('/api/v1/perennia-docs/review/reject', {
      document_ids: documentIds,
      reason,
    });
    return response.data;
  },

  requestDocumentInfo: async (documentId, message) => {
    const response = await api.post(`/api/v1/perennia-docs/review/${documentId}/request-info`, {
      message,
    });
    return response.data;
  },

  // Activity Feed
  getActivityFeed: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/activity-feed', { params });
    return response.data;
  },

  // Loan Document Requirements
  getLoanDocumentRequirements: async (loanId) => {
    const response = await api.get(`/api/v1/perennia-docs/loans/${loanId}/requirements`);
    return response.data;
  },

  updateLoanDocumentRequirements: async (loanId, documentType, data) => {
    const response = await api.patch(
      `/api/v1/perennia-docs/loans/${loanId}/requirements/${documentType}`,
      data
    );
    return response.data;
  },

  // Document Upload (for borrower portal)
  uploadDocument: async (loanId, documentType, file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    const response = await api.post(
      `/api/v1/perennia-docs/loans/${loanId}/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: onProgress
          ? (progressEvent) => {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              onProgress(percentCompleted);
            }
          : undefined,
      }
    );
    return response.data;
  },

  // Get document download URL (signed S3 URL)
  getDocumentUrl: async (documentId) => {
    const response = await api.get(`/api/v1/perennia-docs/documents/${documentId}/url`);
    return response.data;
  },

  // Portal Notifications
  getPortalNotifications: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/portal/notifications', { params });
    return response.data;
  },

  markNotificationRead: async (notificationId) => {
    const response = await api.patch(`/api/v1/perennia-docs/portal/notifications/${notificationId}/read`);
    return response.data;
  },

  markAllNotificationsRead: async () => {
    const response = await api.post('/api/v1/perennia-docs/portal/notifications/read-all');
    return response.data;
  },

  // Send document reminder
  sendDocumentReminder: async (loanId, documentTypes = []) => {
    const response = await api.post(`/api/v1/perennia-docs/loans/${loanId}/remind`, {
      document_types: documentTypes,
    });
    return response.data;
  },
};
