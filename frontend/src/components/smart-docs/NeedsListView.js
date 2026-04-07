import React, { useState, useEffect } from 'react';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './NeedsListView.css';

function NeedsListView({ loanId, borrowerId = 1, borrowerEmail = '', borrowerName = '', borrowerPhone = '', onRequestUpdated }) {
  const [needsList, setNeedsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addingRequest, setAddingRequest] = useState(false);

  const getDefaultDocument = () => ({
    title: '',
    description: '',
    instructions: '',
    priority: 'NORMAL',
    due_date: ''
  });

  const getDefaultNotificationSettings = () => ({
    send_notification: false,
    send_sms: false,
    borrower_email: borrowerEmail || '',
    borrower_name: borrowerName || '',
    borrower_phone: borrowerPhone || ''
  });

  const [documents, setDocuments] = useState([getDefaultDocument()]);
  const [notificationSettings, setNotificationSettings] = useState(getDefaultNotificationSettings);

  // Sync borrower fields when props change (lead data may load after mount)
  useEffect(() => {
    setNotificationSettings(prev => ({
      ...prev,
      borrower_email: prev.borrower_email || borrowerEmail || '',
      borrower_name: prev.borrower_name || borrowerName || '',
      borrower_phone: prev.borrower_phone || borrowerPhone || ''
    }));
  }, [borrowerEmail, borrowerName, borrowerPhone]);

  const updateDocument = (index, field, value) => {
    setDocuments(prev => prev.map((doc, i) => i === index ? { ...doc, [field]: value } : doc));
  };

  const addDocument = () => {
    setDocuments(prev => [...prev, getDefaultDocument()]);
  };

  const removeDocument = (index) => {
    setDocuments(prev => prev.filter((_, i) => i !== index));
  };

  useEffect(() => {
    if (loanId) {
      fetchNeedsList();
    }
  }, [loanId]);

  const fetchNeedsList = async () => {
    try {
      setLoading(true);
      const data = await smartDocsAPI.getNeedsList(loanId);
      // Backend returns all_requests (array) and requests_by_status (object by status)
      setNeedsList(data.all_requests || []);
    } catch (err) {
      console.error('Error fetching needs list:', err);
      setError('Failed to load needs list');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateNeedsList = async () => {
    try {
      setGenerating(true);
      await smartDocsAPI.generateNeedsList({ loan_id: loanId, borrower_id: 1 });
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error generating needs list:', err);
      setError('Failed to generate needs list');
    } finally {
      setGenerating(false);
    }
  };

  const handleMarkFulfilled = async (requestId) => {
    try {
      // For now, just waive as fulfilled
      await smartDocsAPI.waiveRequest(requestId, 'Marked as fulfilled', 1);
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error updating request:', err);
    }
  };

  const handleAddCustomRequest = async (e) => {
    e.preventDefault();

    // Validate all documents have titles
    const emptyIndex = documents.findIndex(doc => !doc.title.trim());
    if (emptyIndex !== -1) {
      setError(`Document #${emptyIndex + 1} is missing a title`);
      return;
    }

    try {
      setAddingRequest(true);
      setError(null);

      const requests = documents.map(doc => ({
        title: doc.title.trim(),
        description: doc.description.trim() || null,
        instructions: doc.instructions.trim() || null,
        priority: doc.priority,
        due_date: doc.due_date || null,
        send_notification: notificationSettings.send_notification,
        send_sms: notificationSettings.send_sms,
        borrower_email: notificationSettings.borrower_email.trim() || null,
        borrower_name: notificationSettings.borrower_name.trim() || null,
        borrower_phone: notificationSettings.borrower_phone.trim() || null
      }));

      const results = await smartDocsAPI.addBulkCustomRequests(loanId, borrowerId, requests);

      // Log notification status for each result
      results.forEach(r => {
        if (r.success && r.result) {
          if (r.result.notification_sent) console.log(`Email notification sent for "${r.title}"`);
          if (r.result.sms_sent) console.log(`SMS notification sent for "${r.title}"`);
        }
      });

      const failures = results.filter(r => !r.success);
      if (failures.length > 0) {
        setError(`${failures.length} of ${results.length} requests failed: ${failures.map(f => f.title).join(', ')}`);
      }

      // Reset form and close modal
      setDocuments([getDefaultDocument()]);
      setNotificationSettings(getDefaultNotificationSettings());
      setShowAddModal(false);

      // Refresh the list
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error adding custom request:', err);
      setError('Failed to add document requests');
    } finally {
      setAddingRequest(false);
    }
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    setDocuments([getDefaultDocument()]);
    setNotificationSettings(getDefaultNotificationSettings());
    setError(null);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'fulfilled': return 'green';
      case 'expired': return 'red';
      case 'waived': return 'gray';
      default: return 'orange';
    }
  };

  const getPriorityLabel = (priority) => {
    // Handle both string and number priority values
    const priorityStr = String(priority).toUpperCase();
    switch (priorityStr) {
      case 'CRITICAL': case '1': return { label: 'Critical', class: 'critical' };
      case 'HIGH': case '2': return { label: 'High', class: 'high' };
      case 'NORMAL': case 'MEDIUM': case '3': return { label: 'Normal', class: 'medium' };
      case 'LOW': default: return { label: 'Low', class: 'low' };
    }
  };

  if (loading) {
    return <div className="needs-list-loading">Loading needs list...</div>;
  }

  return (
    <div className="needs-list-view">
      <div className="needs-list-header">
        <h3>Document Needs List</h3>
        <div className="needs-list-actions">
          <button
            className="add-request-btn"
            onClick={() => setShowAddModal(true)}
          >
            + Add Request
          </button>
          <button
            className="generate-btn"
            onClick={handleGenerateNeedsList}
            disabled={generating}
          >
            {generating ? 'Generating...' : 'Generate/Refresh List'}
          </button>
        </div>
      </div>

      {error && <div className="needs-list-error">{error}</div>}

      {/* Add Custom Request Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-content add-request-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Request Document{documents.length > 1 ? 's' : ''}</h3>
              <button className="modal-close" onClick={handleCloseModal}>×</button>
            </div>
            <form onSubmit={handleAddCustomRequest}>
              <div className="document-entries">
                {documents.map((doc, index) => (
                  <div key={index} className="document-entry-card">
                    <div className="document-entry-header">
                      <span className="document-entry-number">Document {index + 1}</span>
                      {documents.length > 1 && (
                        <button
                          type="button"
                          className="document-entry-remove"
                          onClick={() => removeDocument(index)}
                          title="Remove this document"
                        >
                          ×
                        </button>
                      )}
                    </div>
                    <div className="form-group">
                      <label htmlFor={`title-${index}`}>Document Title *</label>
                      <input
                        type="text"
                        id={`title-${index}`}
                        value={doc.title}
                        onChange={(e) => updateDocument(index, 'title', e.target.value)}
                        placeholder="e.g., Bank Statement - Chase"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor={`description-${index}`}>Description</label>
                      <textarea
                        id={`description-${index}`}
                        value={doc.description}
                        onChange={(e) => updateDocument(index, 'description', e.target.value)}
                        placeholder="What document is needed and why"
                        rows={2}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor={`instructions-${index}`}>Instructions for Borrower</label>
                      <textarea
                        id={`instructions-${index}`}
                        value={doc.instructions}
                        onChange={(e) => updateDocument(index, 'instructions', e.target.value)}
                        placeholder="Instructions on how to obtain or submit this document"
                        rows={3}
                      />
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor={`priority-${index}`}>Priority</label>
                        <select
                          id={`priority-${index}`}
                          value={doc.priority}
                          onChange={(e) => updateDocument(index, 'priority', e.target.value)}
                        >
                          <option value="LOW">Low</option>
                          <option value="NORMAL">Normal</option>
                          <option value="HIGH">High</option>
                          <option value="CRITICAL">Critical</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label htmlFor={`due_date-${index}`}>Due Date</label>
                        <input
                          type="date"
                          id={`due_date-${index}`}
                          value={doc.due_date}
                          onChange={(e) => updateDocument(index, 'due_date', e.target.value)}
                          min={new Date().toISOString().split('T')[0]}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <button
                type="button"
                className="add-another-doc-btn"
                onClick={addDocument}
              >
                + Add Another Document
              </button>

              {/* Notification Section */}
              <div className="notification-section">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={notificationSettings.send_notification}
                    onChange={(e) => setNotificationSettings({ ...notificationSettings, send_notification: e.target.checked })}
                  />
                  <span>Send email notification to borrower</span>
                </label>

                <label className="checkbox-label" style={{ marginTop: '8px' }}>
                  <input
                    type="checkbox"
                    checked={notificationSettings.send_sms}
                    onChange={(e) => setNotificationSettings({ ...notificationSettings, send_sms: e.target.checked })}
                  />
                  <span>Send SMS notification to borrower</span>
                </label>

                {(notificationSettings.send_notification || notificationSettings.send_sms) && (
                  <div className="notification-fields">
                    <div className="form-group">
                      <label htmlFor="borrower_name">Borrower Name</label>
                      <input
                        type="text"
                        id="borrower_name"
                        value={notificationSettings.borrower_name}
                        onChange={(e) => setNotificationSettings({ ...notificationSettings, borrower_name: e.target.value })}
                        placeholder="Borrower name"
                      />
                    </div>
                    {notificationSettings.send_notification && (
                      <div className="form-group">
                        <label htmlFor="borrower_email">Borrower Email *</label>
                        <input
                          type="email"
                          id="borrower_email"
                          value={notificationSettings.borrower_email}
                          onChange={(e) => setNotificationSettings({ ...notificationSettings, borrower_email: e.target.value })}
                          placeholder="borrower@email.com"
                          required={notificationSettings.send_notification}
                        />
                      </div>
                    )}
                    {notificationSettings.send_sms && (
                      <div className="form-group">
                        <label htmlFor="borrower_phone">Borrower Phone *</label>
                        <input
                          type="tel"
                          id="borrower_phone"
                          value={notificationSettings.borrower_phone}
                          onChange={(e) => setNotificationSettings({ ...notificationSettings, borrower_phone: e.target.value })}
                          placeholder="(555) 123-4567"
                          required={notificationSettings.send_sms}
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={handleCloseModal}>
                  Cancel
                </button>
                <button type="submit" className="btn-submit" disabled={addingRequest}>
                  {addingRequest
                    ? 'Adding...'
                    : documents.length === 1
                      ? 'Add Request'
                      : `Add ${documents.length} Requests`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {needsList.length === 0 ? (
        <div className="needs-list-empty">
          <p>No document requests yet.</p>
          <p>Click "Generate/Refresh List" to create a needs list based on loan requirements.</p>
        </div>
      ) : (
        <div className="needs-list-items">
          {needsList.map((request) => {
            const priority = getPriorityLabel(request.priority);
            // Map backend status values (OPEN, PENDING_REVIEW, ACCEPTED, etc.) to display
            const statusDisplay = (request.status || 'OPEN').toLowerCase().replace('_', '-');
            const isOpen = ['open', 'pending_review'].includes((request.status || '').toLowerCase());
            return (
              <div key={request.id} className={`needs-item status-${statusDisplay}`}>
                <div className="needs-item-header">
                  <span className={`priority-badge ${priority.class}`}>{priority.label}</span>
                  <span className={`status-badge ${statusDisplay}`}>
                    {(request.status || 'OPEN').replace('_', ' ')}
                  </span>
                </div>
                <h4>{request.title || request.doc_type}</h4>
                <p className="description">{request.description}</p>
                {request.instructions && (
                  <p className="instructions"><em>Instructions: {request.instructions}</em></p>
                )}
                <div className="needs-item-meta">
                  {request.doc_type && (
                    <span className="doc-type">Type: {request.doc_type}</span>
                  )}
                  {request.required_count > 1 && (
                    <span className="required-count">Required: {request.required_count}</span>
                  )}
                  {request.freshness_days && (
                    <span className="freshness">Freshness: {request.freshness_days} days</span>
                  )}
                  {request.due_date && (
                    <span className="due-date">Due: {new Date(request.due_date).toLocaleDateString()}</span>
                  )}
                </div>
                {isOpen && (
                  <div className="needs-item-actions">
                    <button
                      className="btn-small btn-fulfill"
                      onClick={() => handleMarkFulfilled(request.id)}
                    >
                      Mark Fulfilled
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default NeedsListView;
