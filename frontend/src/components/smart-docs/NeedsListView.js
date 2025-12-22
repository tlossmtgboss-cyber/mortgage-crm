import React, { useState, useEffect } from 'react';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './NeedsListView.css';

function NeedsListView({ loanId, borrowerId = 1, onRequestUpdated }) {
  const [needsList, setNeedsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addingRequest, setAddingRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({
    title: '',
    description: '',
    instructions: '',
    priority: 'NORMAL',
    due_date: '',
    send_notification: false,
    borrower_email: '',
    borrower_name: ''
  });

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
    if (!newRequest.title.trim()) {
      setError('Document title is required');
      return;
    }

    try {
      setAddingRequest(true);
      setError(null);

      const requestData = {
        title: newRequest.title.trim(),
        description: newRequest.description.trim() || null,
        instructions: newRequest.instructions.trim() || null,
        priority: newRequest.priority,
        due_date: newRequest.due_date || null,
        send_notification: newRequest.send_notification,
        borrower_email: newRequest.borrower_email.trim() || null,
        borrower_name: newRequest.borrower_name.trim() || null
      };

      const result = await smartDocsAPI.addCustomRequest(loanId, borrowerId, requestData);

      // Show notification status
      if (result.notification_sent) {
        console.log('Email notification sent to borrower');
      }

      // Reset form and close modal
      setNewRequest({
        title: '',
        description: '',
        instructions: '',
        priority: 'NORMAL',
        due_date: '',
        send_notification: false,
        borrower_email: '',
        borrower_name: ''
      });
      setShowAddModal(false);

      // Refresh the list
      await fetchNeedsList();
      if (onRequestUpdated) onRequestUpdated();
    } catch (err) {
      console.error('Error adding custom request:', err);
      setError('Failed to add document request');
    } finally {
      setAddingRequest(false);
    }
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    setNewRequest({
      title: '',
      description: '',
      instructions: '',
      priority: 'NORMAL',
      due_date: ''
    });
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
              <h3>Request Document</h3>
              <button className="modal-close" onClick={handleCloseModal}>×</button>
            </div>
            <form onSubmit={handleAddCustomRequest}>
              <div className="form-group">
                <label htmlFor="title">Document Title *</label>
                <input
                  type="text"
                  id="title"
                  value={newRequest.title}
                  onChange={(e) => setNewRequest({ ...newRequest, title: e.target.value })}
                  placeholder="e.g., Bank Statement - Chase"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="description">Description</label>
                <textarea
                  id="description"
                  value={newRequest.description}
                  onChange={(e) => setNewRequest({ ...newRequest, description: e.target.value })}
                  placeholder="What document is needed and why"
                  rows={2}
                />
              </div>
              <div className="form-group">
                <label htmlFor="instructions">Instructions for Borrower</label>
                <textarea
                  id="instructions"
                  value={newRequest.instructions}
                  onChange={(e) => setNewRequest({ ...newRequest, instructions: e.target.value })}
                  placeholder="Instructions on how to obtain or submit this document"
                  rows={3}
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="priority">Priority</label>
                  <select
                    id="priority"
                    value={newRequest.priority}
                    onChange={(e) => setNewRequest({ ...newRequest, priority: e.target.value })}
                  >
                    <option value="LOW">Low</option>
                    <option value="NORMAL">Normal</option>
                    <option value="HIGH">High</option>
                    <option value="CRITICAL">Critical</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="due_date">Due Date</label>
                  <input
                    type="date"
                    id="due_date"
                    value={newRequest.due_date}
                    onChange={(e) => setNewRequest({ ...newRequest, due_date: e.target.value })}
                    min={new Date().toISOString().split('T')[0]}
                  />
                </div>
              </div>

              {/* Email Notification Section */}
              <div className="notification-section">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={newRequest.send_notification}
                    onChange={(e) => setNewRequest({ ...newRequest, send_notification: e.target.checked })}
                  />
                  <span>Send email notification to borrower</span>
                </label>

                {newRequest.send_notification && (
                  <div className="notification-fields">
                    <div className="form-group">
                      <label htmlFor="borrower_email">Borrower Email *</label>
                      <input
                        type="email"
                        id="borrower_email"
                        value={newRequest.borrower_email}
                        onChange={(e) => setNewRequest({ ...newRequest, borrower_email: e.target.value })}
                        placeholder="borrower@email.com"
                        required={newRequest.send_notification}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="borrower_name">Borrower Name</label>
                      <input
                        type="text"
                        id="borrower_name"
                        value={newRequest.borrower_name}
                        onChange={(e) => setNewRequest({ ...newRequest, borrower_name: e.target.value })}
                        placeholder="John Smith"
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={handleCloseModal}>
                  Cancel
                </button>
                <button type="submit" className="btn-submit" disabled={addingRequest}>
                  {addingRequest ? 'Adding...' : 'Add Request'}
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
