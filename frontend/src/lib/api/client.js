/**
 * Perennia API Client
 *
 * Centralized API client for communicating with the FastAPI backend.
 * Provides typed methods for all portal and integration endpoints.
 */

// Determine API base URL at runtime (not build time)
// In production: use empty string for relative URLs (Vercel rewrites handle proxying)
// In development: use localhost:8000
function getApiBaseUrl() {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    // Production: ALWAYS use relative URLs for Vercel rewrites
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      return '';
    }
  }
  // Development default
  return process.env.REACT_APP_API_URL || 'http://localhost:8000';
}

// Call at runtime, not module load time
let FASTAPI_BASE_URL = null;

class PerenniaAPIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'PerenniaAPIError';
    this.status = status;
    this.data = data;
  }
}

class PerenniaAPI {
  constructor(baseUrl = null) {
    // Lazy initialization of baseUrl at runtime
    this.baseUrl = baseUrl !== null ? baseUrl : getApiBaseUrl();
    this.authToken = null;
    console.log('[PerenniaAPI] Initialized with baseUrl:', this.baseUrl || '(empty - using relative URLs)');
  }

  /**
   * Set authentication token for API requests
   */
  setAuthToken(token) {
    this.authToken = token;
  }

  /**
   * Clear authentication token
   */
  clearAuthToken() {
    this.authToken = null;
  }

  // ==========================================================================
  // PORTAL AI ASSISTANT
  // ==========================================================================

  /**
   * Chat with AI assistant
   * @param {Object} params
   * @param {number} params.workspaceId - Workspace ID
   * @param {string} params.message - User message
   * @param {Array} params.conversationHistory - Previous messages
   * @param {Object} params.context - Additional context
   */
  async chatWithAssistant({ workspaceId, message, conversationHistory = [], context = null }) {
    return this.post('/api/v1/portal-assistant/chat', {
      workspace_id: workspaceId,
      message,
      conversation_history: conversationHistory,
      context,
    });
  }

  /**
   * Get quick actions for workspace
   * @param {number} workspaceId
   */
  async getQuickActions(workspaceId) {
    return this.get(`/api/v1/portal-assistant/quick-actions/${workspaceId}`);
  }

  /**
   * Get FAQ list
   */
  async getFAQ() {
    return this.get('/api/v1/portal-assistant/faq');
  }

  /**
   * Get contextual tips for workspace
   * @param {number} workspaceId
   */
  async getTips(workspaceId) {
    return this.get(`/api/v1/portal-assistant/tips/${workspaceId}`);
  }

  /**
   * Submit feedback for AI assistant
   * @param {Object} params
   */
  async submitAssistantFeedback({ workspaceId, messageId, rating, feedback }) {
    return this.post('/api/v1/portal-assistant/feedback', {
      workspace_id: workspaceId,
      message_id: messageId,
      rating,
      feedback,
    });
  }

  // ==========================================================================
  // PURL INTEGRATION
  // ==========================================================================

  /**
   * Initialize document requirements for workspace
   * @param {number} workspaceId
   * @param {Object} params
   */
  async initializeWorkspaceDocuments(workspaceId, { templatePackId, loanType, employmentType, propertyType } = {}) {
    return this.post(`/api/v1/purl-integration/workspaces/${workspaceId}/initialize-documents`, {
      template_pack_id: templatePackId,
      loan_type: loanType,
      employment_type: employmentType,
      property_type: propertyType,
    });
  }

  /**
   * Get comprehensive document status for workspace
   * @param {number} workspaceId
   */
  async getWorkspaceDocumentStatus(workspaceId) {
    return this.get(`/api/v1/purl-integration/workspaces/${workspaceId}/document-status`);
  }

  /**
   * Get unified activity feed
   * @param {number} workspaceId
   * @param {Object} params
   */
  async getWorkspaceActivityFeed(workspaceId, { limit = 50, offset = 0 } = {}) {
    const query = new URLSearchParams({ limit, offset }).toString();
    return this.get(`/api/v1/purl-integration/workspaces/${workspaceId}/activity-feed?${query}`);
  }

  /**
   * Get workspace milestones
   * @param {number} workspaceId
   */
  async getWorkspaceMilestones(workspaceId) {
    return this.get(`/api/v1/purl-integration/workspaces/${workspaceId}/milestones`);
  }

  /**
   * Update milestone status
   * @param {number} workspaceId
   * @param {number} milestoneId
   * @param {Object} data
   */
  async updateMilestone(workspaceId, milestoneId, { status, notes, autoNotify = true }) {
    return this.patch(`/api/v1/purl-integration/workspaces/${workspaceId}/milestones/${milestoneId}`, {
      milestone_id: milestoneId,
      status,
      notes,
      auto_notify: autoNotify,
    });
  }

  /**
   * Get workspace notifications
   * @param {number} workspaceId
   * @param {Object} params
   */
  async getWorkspaceNotifications(workspaceId, { unreadOnly = false, limit = 20 } = {}) {
    const query = new URLSearchParams({ unread_only: unreadOnly, limit }).toString();
    return this.get(`/api/v1/purl-integration/workspaces/${workspaceId}/notifications?${query}`);
  }

  /**
   * Mark notification as read
   * @param {number} workspaceId
   * @param {number} notificationId
   */
  async markNotificationRead(workspaceId, notificationId) {
    return this.patch(
      `/api/v1/purl-integration/workspaces/${workspaceId}/notifications/${notificationId}/read`,
      {}
    );
  }

  /**
   * Mark all notifications as read
   * @param {number} workspaceId
   */
  async markAllNotificationsRead(workspaceId) {
    return this.patch(
      `/api/v1/purl-integration/workspaces/${workspaceId}/notifications/mark-all-read`,
      {}
    );
  }

  /**
   * Sync workspace status based on current state
   * @param {number} workspaceId
   */
  async syncWorkspaceStatus(workspaceId) {
    return this.post(`/api/v1/purl-integration/workspaces/${workspaceId}/sync-status`, {});
  }

  // ==========================================================================
  // DOCUMENT MANAGEMENT
  // ==========================================================================

  /**
   * Initiate document upload (get presigned URL)
   * @param {Object} params
   */
  async initiateDocumentUpload({ workspaceId, requestId, fileName, fileSize, mimeType, documentType, documentSubtype }) {
    return this.post('/api/v1/portal/documents/upload/initiate', {
      workspace_id: workspaceId,
      request_id: requestId,
      file_name: fileName,
      file_size: fileSize,
      mime_type: mimeType,
      document_type: documentType,
      document_subtype: documentSubtype,
    });
  }

  /**
   * Confirm document upload completion
   * @param {Object} params
   */
  async confirmDocumentUpload({ workspaceId, documentId, etag }) {
    return this.post('/api/v1/portal/documents/upload/confirm', {
      workspace_id: workspaceId,
      document_id: documentId,
      etag,
    });
  }

  /**
   * Get document preview URL
   * @param {number} documentId
   * @param {number} workspaceId
   */
  async getDocumentPreview(documentId, workspaceId) {
    return this.get(`/api/v1/portal/documents/${documentId}/preview?workspace_id=${workspaceId}`);
  }

  /**
   * Get document download URL
   * @param {number} documentId
   * @param {number} workspaceId
   */
  async getDocumentDownload(documentId, workspaceId) {
    return this.get(`/api/v1/portal/documents/${documentId}/download?workspace_id=${workspaceId}`);
  }

  /**
   * List documents for workspace
   * @param {number} workspaceId
   * @param {Object} params
   */
  async listWorkspaceDocuments(workspaceId, { status, docType, limit = 50, offset = 0 } = {}) {
    const params = new URLSearchParams({ limit, offset });
    if (status) params.set('status', status);
    if (docType) params.set('doc_type', docType);
    return this.get(`/api/v1/portal/documents/workspace/${workspaceId}?${params.toString()}`);
  }

  /**
   * Review document (admin)
   * @param {number} documentId
   * @param {Object} params
   */
  async reviewDocument(documentId, { action, rejectionReason, notes, notifyBorrower = true }) {
    return this.post(`/api/v1/portal/documents/${documentId}/review`, {
      action,
      rejection_reason: rejectionReason,
      notes,
      notify_borrower: notifyBorrower,
    });
  }

  // ==========================================================================
  // ADMIN DOCUMENT REVIEW QUEUE
  // ==========================================================================

  /**
   * Get document review queue (admin)
   * @param {Object} params
   */
  async getDocumentReviewQueue({ page = 1, limit = 20, status, documentType, search } = {}) {
    const params = new URLSearchParams({ page, limit });
    if (status) params.set('status', status);
    if (documentType) params.set('document_type', documentType);
    if (search) params.set('search', search);
    return this.get(`/api/v1/perennia-docs/review-queue?${params.toString()}`);
  }

  /**
   * Bulk approve documents (admin)
   * @param {Array} documentIds
   */
  async bulkApproveDocuments(documentIds) {
    return this.post('/api/v1/perennia-docs/review/approve', {
      document_ids: documentIds,
    });
  }

  /**
   * Bulk reject documents (admin)
   * @param {Array} documentIds
   * @param {string} reason
   */
  async bulkRejectDocuments(documentIds, reason) {
    return this.post('/api/v1/perennia-docs/review/reject', {
      document_ids: documentIds,
      reason,
    });
  }

  /**
   * Request additional info for document (admin)
   * @param {number} documentId
   * @param {string} message
   */
  async requestDocumentInfo(documentId, message) {
    return this.post(`/api/v1/perennia-docs/review/${documentId}/request-info`, {
      message,
    });
  }

  // ==========================================================================
  // AUTHENTICATION
  // ==========================================================================

  /**
   * Send magic link to borrower
   * @param {Object} params
   */
  async sendMagicLink({ workspaceId, email, redirectPath }) {
    return this.post('/api/v1/auth/portal/send-link', {
      workspace_id: workspaceId,
      email,
      redirect_path: redirectPath,
    });
  }

  /**
   * Verify magic link token
   * @param {string} token
   */
  async verifyMagicLink(token) {
    return this.post('/api/v1/auth/portal/verify', { token });
  }

  /**
   * Get current session info
   */
  async getSessionInfo() {
    return this.get('/api/v1/auth/portal/session');
  }

  /**
   * Refresh current session
   */
  async refreshSession() {
    return this.post('/api/v1/auth/portal/refresh', {});
  }

  /**
   * Logout
   */
  async logout() {
    return this.post('/api/v1/auth/portal/logout', {});
  }

  // ==========================================================================
  // PURL WORKSPACE (Direct PURL endpoints)
  // ==========================================================================

  /**
   * Get workspace data
   * @param {string} slug
   */
  async getWorkspaceData(slug) {
    return this.get(`/api/purl/workspace/${slug}`);
  }

  /**
   * Get workspace status
   * @param {string} slug
   */
  async getWorkspaceStatus(slug) {
    return this.get(`/api/purl/workspace/${slug}/status`);
  }

  /**
   * Get the borrower-facing loan dashboard aggregator.
   *
   * This is PURL-token authed (GET /api/v1/portal/borrower/{crmLoanId}/dashboard,
   * Depends(require_purl_token)) and returns
   * { lifecycle, milestone_progress, countdown, documents, recent_activity,
   *   risks, home_value }. The PURL access token already set via setAuthToken
   * is attached on the standard Bearer path.
   *
   * IMPORTANT: crmLoanId is the CRM Loan.id, surfaced to the frontend as
   * `data.loan.crm_loan_id` (PURLLoan.main_loan_id). Do NOT pass
   * `data.loan.id` (PURLLoan.id) — that is a different, disjoint id-space and
   * will resolve to the wrong loan (or 404).
   *
   * @param {number|string} crmLoanId - CRM Loan.id (data.loan.crm_loan_id)
   */
  async getBorrowerDashboard(crmLoanId) {
    return this.get(`/api/v1/portal/borrower/${crmLoanId}/dashboard`);
  }

  /**
   * Get post-close data for MUM portal
   * @param {string} slug
   */
  async getPostcloseData(slug) {
    return this.get(`/api/purl/workspace/${slug}/postclose-data`);
  }

  /**
   * Get workspace application
   * @param {string} slug
   */
  async getWorkspaceApplication(slug) {
    return this.get(`/api/purl/workspace/${slug}/application`);
  }

  /**
   * Save application data
   * @param {string} slug
   * @param {Object} data
   */
  async saveApplication(slug, data) {
    return this.post(`/api/purl/workspace/${slug}/application`, data);
  }

  /**
   * Submit application
   * @param {string} slug
   */
  async submitApplication(slug) {
    return this.post(`/api/purl/workspace/${slug}/application/submit`, {});
  }

  /**
   * Get workspace documents
   * @param {string} slug
   * @param {Object} params
   */
  async getWorkspaceDocuments(slug, { category } = {}) {
    const params = category ? `?category=${category}` : '';
    return this.get(`/api/purl/workspace/${slug}/documents${params}`);
  }

  /**
   * Get document upload URL
   * @param {string} slug
   * @param {Object} params
   */
  async getDocumentUploadUrl(slug, { filename, contentType, documentType }) {
    const params = new URLSearchParams({
      filename,
      content_type: contentType,
      document_type: documentType || '',
    });
    return this.post(`/api/purl/workspace/${slug}/documents/upload-url?${params.toString()}`);
  }

  /**
   * Complete document upload
   * @param {string} slug
   * @param {Object} params
   */
  async completeDocumentUpload(slug, { documentKey, filename, fileSize, contentType, documentType }) {
    const params = new URLSearchParams({
      document_key: documentKey,
      filename,
      file_size: fileSize,
      content_type: contentType,
      document_type: documentType || '',
    });
    return this.post(`/api/purl/workspace/${slug}/documents/upload-complete?${params.toString()}`);
  }

  /**
   * Direct document upload (fallback when S3 not configured)
   * @param {string} slug
   * @param {File} file
   * @param {string} documentType
   */
  async uploadDocumentDirect(slug, file, documentType = '') {
    const formData = new FormData();
    formData.append('file', file);
    if (documentType) {
      formData.append('document_type', documentType);
    }

    const url = `${this.baseUrl}/api/purl/workspace/${slug}/documents/upload-direct`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: this.authToken ? { 'Authorization': `Bearer ${this.authToken}` } : {},
      credentials: 'include',
    });

    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new PerenniaAPIError(
        data?.detail || data?.message || `HTTP ${response.status}`,
        response.status,
        data
      );
    }

    return response.json();
  }

  /**
   * Get workspace tasks
   * @param {string} slug
   * @param {Object} params
   */
  async getWorkspaceTasks(slug, { status } = {}) {
    const params = status ? `?status=${status}` : '';
    return this.get(`/api/purl/workspace/${slug}/tasks${params}`);
  }

  /**
   * Update task
   * @param {string} slug
   * @param {number} taskId
   * @param {Object} update
   */
  async updateTask(slug, taskId, update) {
    return this.patch(`/api/purl/workspace/${slug}/tasks/${taskId}`, update);
  }

  /**
   * Get workspace timeline
   * @param {string} slug
   * @param {Object} params
   */
  async getWorkspaceTimeline(slug, { limit = 50 } = {}) {
    return this.get(`/api/purl/workspace/${slug}/timeline?limit=${limit}`);
  }

  /**
   * Get workspace messages
   * @param {string} slug
   * @param {Object} params
   */
  async getWorkspaceMessages(slug, { limit = 50, offset = 0 } = {}) {
    return this.get(`/api/purl/workspace/${slug}/messages?limit=${limit}&offset=${offset}`);
  }

  /**
   * Send message
   * @param {string} slug
   * @param {Object} message
   */
  async sendMessage(slug, { messageType = 'text', content }) {
    return this.post(`/api/purl/workspace/${slug}/messages`, {
      message_type: messageType,
      content,
    });
  }

  // ==========================================================================
  // CONDITIONS (NEEDS LIST)
  // ==========================================================================

  /**
   * Get workspace conditions (needs list)
   * @param {string} slug
   * @param {Object} params
   */
  async getWorkspaceConditions(slug, { status } = {}) {
    const params = status ? `?status=${status}` : '';
    return this.get(`/api/purl/workspace/${slug}/conditions${params}`);
  }

  /**
   * Mark condition as received
   * @param {string} slug
   * @param {number} conditionId
   */
  async markConditionReceived(slug, conditionId) {
    return this.patch(`/api/purl/workspace/${slug}/conditions/${conditionId}/mark-received`, {});
  }

  // ==========================================================================
  // HTTP METHODS
  // ==========================================================================

  async get(path) {
    return this.request('GET', path);
  }

  async post(path, data) {
    return this.request('POST', path, data);
  }

  async patch(path, data) {
    return this.request('PATCH', path, data);
  }

  async put(path, data) {
    return this.request('PUT', path, data);
  }

  async delete(path) {
    return this.request('DELETE', path);
  }

  async request(method, path, data = null) {
    const url = `${this.baseUrl}${path}`;
    const options = {
      method,
      headers: this.getHeaders(),
      credentials: 'include', // Include cookies
    };

    if (data && method !== 'GET') {
      options.body = JSON.stringify(data);
    }

    try {
      const response = await fetch(url, options);
      return await this.handleResponse(response);
    } catch (error) {
      if (error instanceof PerenniaAPIError) {
        throw error;
      }
      throw new PerenniaAPIError(
        error.message || 'Network error',
        0,
        null
      );
    }
  }

  getHeaders() {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }

    return headers;
  }

  async handleResponse(response) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      const message = data?.detail || data?.message || data?.error || `HTTP ${response.status}`;
      throw new PerenniaAPIError(message, response.status, data);
    }

    return data;
  }
}

// Export singleton instance
export const api = new PerenniaAPI();

// Export class for custom instances
export { PerenniaAPI, PerenniaAPIError };

// Export base URL function for direct usage
export { getApiBaseUrl };
