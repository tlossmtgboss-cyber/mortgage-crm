import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './ReconciliationCenter.css';

function ReconciliationCenter() {
  const [activeTab, setActiveTab] = useState('pending'); // 'pending', 'pendingReview', or 'completed'
  const [pendingItems, setPendingItems] = useState([]);
  const [pendingReviewItems, setPendingReviewItems] = useState([]);
  const [completedItems, setCompletedItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState(null);
  const [editedFields, setEditedFields] = useState({});
  const [processingAction, setProcessingAction] = useState(false);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [selectedReviewItems, setSelectedReviewItems] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [approvalProgress, setApprovalProgress] = useState({ approved: 0, total: 20 });
  const [delegateToAI, setDelegateToAI] = useState(false);

  useEffect(() => {
    fetchPendingItems();
    fetchCompletedItems();
    // Note: loadSampleData() removed - was overwriting real API data with samples

    // Auto-sync emails every 5 minutes
    const syncInterval = setInterval(() => {
      syncEmails(true); // silent sync
    }, 5 * 60 * 1000); // 5 minutes

    // Initial sync on load
    syncEmails(true);

    return () => clearInterval(syncInterval);
  }, []);

  const fetchPendingItems = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const allItems = data.items || [];

        // Split items: high confidence goes to auto-processing, low confidence needs review
        const autoProcess = [];
        const needsReview = [];

        allItems.forEach(item => {
          // Items with low confidence or specific flags go to pending review
          if (item.ai_confidence < 0.75 || item.match_confidence < 0.65 || item.status === 'needs_review') {
            needsReview.push({
              ...item,
              needs_human_review: true,
              review_reason: item.ai_confidence < 0.75 ? 'Low AI confidence' :
                            item.match_confidence < 0.65 ? 'Low match confidence' :
                            'Flagged for review',
              email_subject: item.email?.subject,
              email_from: item.email?.sender,
              email_received_at: item.email?.received_at,
              email_body: item.email?.body || item.email?.text_content || item.email?.html_content
            });
          } else {
            autoProcess.push(item);
          }
        });

        setPendingItems(autoProcess);
        setPendingReviewItems(needsReview);
      }
    } catch (error) {
      console.error('Error fetching pending items:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompletedItems = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/completed?limit=50`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setCompletedItems(data.items || []);
      }
    } catch (error) {
      console.error('Error fetching completed items:', error);
    }
  };

  const syncEmails = async (silent = false) => {
    try {
      if (!silent) {
        setSyncingEmails(true);
        setSyncStatus('Syncing emails...');
      }

      const token = localStorage.getItem('token');

      // Check which email service is connected
      const gmailStatus = await fetch(`${API_BASE_URL}/api/v1/gmail/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);

      const microsoftStatus = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      }).then(r => r.ok ? r.json() : null).catch(() => null);

      let response;
      let syncEndpoint;

      if (gmailStatus?.connected) {
        // Use Gmail sync
        syncEndpoint = `${API_BASE_URL}/api/v1/gmail/sync`;
        response = await fetch(syncEndpoint, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
      } else if (microsoftStatus?.connected) {
        // Use Microsoft sync
        syncEndpoint = `${API_BASE_URL}/api/v1/microsoft/sync-now`;
        response = await fetch(syncEndpoint, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
      } else {
        // No email service connected
        if (!silent) {
          setSyncStatus('⚠ No email service connected. Go to Settings to connect Gmail or Microsoft 365.');
          setTimeout(() => setSyncStatus(''), 5000);
        }
        return;
      }

      if (response.ok) {
        const data = await response.json();
        setLastSyncTime(new Date());

        if (!silent) {
          const count = data.processed_count || data.synced_count || 0;
          setSyncStatus(`✓ Synced ${count} emails successfully`);
          // Refresh both pending and completed items to show new data
          fetchPendingItems();
          fetchCompletedItems();

          // Clear status after 3 seconds
          setTimeout(() => setSyncStatus(''), 3000);
        }
      } else {
        if (!silent) {
          // Try to get specific error message
          let errorMessage = '⚠ Sync failed - please try again';
          try {
            const errorData = await response.json();
            if (response.status === 404 && errorData.detail) {
              // Not connected error
              errorMessage = `⚠ ${errorData.detail}. Go to Settings to reconnect.`;
            } else if (errorData.detail) {
              errorMessage = `⚠ ${errorData.detail}`;
            }
          } catch (e) {
            // Use default error message
          }
          setSyncStatus(errorMessage);
          setTimeout(() => setSyncStatus(''), 5000);
        }
      }
    } catch (error) {
      console.error('Error syncing emails:', error);
      if (!silent) {
        setSyncStatus('⚠ Sync failed - please try again');
        setTimeout(() => setSyncStatus(''), 3000);
      }
    } finally {
      if (!silent) {
        setSyncingEmails(false);
      }
    }
  };

  const handleApprove = async (itemId) => {
    try {
      setProcessingAction(true);
      const corrections = Object.keys(editedFields).length > 0 ? editedFields : null;

      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          corrections: corrections,
          delegate_to_ai: delegateToAI,
          email_intent: selectedItem?.email_intent,
          recommended_action: selectedItem?.recommended_action
        })
      });

      if (response.ok) {
        // Remove from list and reset
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        setDelegateToAI(false);
        // Refresh completed items to show the newly approved item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(`Failed to approve item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error approving item:', error);
      alert(`Error approving item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleReject = async (itemId, reason) => {
    try {
      setProcessingAction(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          extracted_data_id: itemId,
          reason: reason
        })
      });

      if (response.ok) {
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setPendingReviewItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
        // Refresh completed items to show the rejected item
        fetchCompletedItems();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(`Failed to reject item: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error rejecting item:', error);
      alert(`Error rejecting item: ${error.message}`);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleFieldEdit = (fieldName, newValue) => {
    setEditedFields(prev => ({
      ...prev,
      [fieldName]: newValue
    }));
  };

  const toggleItemSelection = (itemId) => {
    setSelectedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        // Limit to 20 items
        if (newSet.size < 20) {
          newSet.add(itemId);
        }
      }
      return newSet;
    });
  };

  const selectAll = () => {
    const itemsToSelect = pendingItems.slice(0, 20).map(item => item.id);
    setSelectedItems(new Set(itemsToSelect));
  };

  const deselectAll = () => {
    setSelectedItems(new Set());
  };

  const bulkApprove = async () => {
    if (selectedItems.size === 0) {
      alert('Please select items to approve');
      return;
    }

    if (!window.confirm(`Approve ${selectedItems.size} loan updates?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            corrections: null
          })
        });

        if (response.ok) {
          successCount++;
          setApprovalProgress(prev => ({
            ...prev,
            approved: prev.approved + 1
          }));
        }
      } catch (error) {
        console.error(`Error approving item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully approved ${successCount} out of ${selectedItems.size} items`);
  };

  const bulkReject = async () => {
    if (selectedItems.size === 0) {
      alert('Please select items to reject');
      return;
    }

    const reason = prompt('Enter reason for rejection:');
    if (!reason) return;

    if (!window.confirm(`Reject ${selectedItems.size} loan updates?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: reason
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error rejecting item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully rejected ${successCount} out of ${selectedItems.size} items`);
  };

  // Pending Review bulk selection functions
  const toggleReviewItemSelection = (itemId) => {
    setSelectedReviewItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  const selectAllReviewItems = () => {
    const itemsToSelect = pendingReviewItems.map(item => item.id);
    setSelectedReviewItems(new Set(itemsToSelect));
  };

  const deselectAllReviewItems = () => {
    setSelectedReviewItems(new Set());
  };

  const bulkDeleteReviewItems = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to delete');
      return;
    }

    if (!window.confirm(`Delete ${selectedReviewItems.size} pending review item(s)? This action cannot be undone.`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: 'Bulk deleted by user'
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error deleting item ${itemId}:`, error);
      }
    }

    // Refresh the list
    await fetchPendingItems();

    // Clear selections
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);

    alert(`Successfully deleted ${successCount} out of ${selectedReviewItems.size} items`);
  };

  const bulkApproveReviewItems = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to approve');
      return;
    }

    if (!window.confirm(`Approve ${selectedReviewItems.size} item(s) and apply to matching records?`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            corrections: null
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error approving item ${itemId}:`, error);
      }
    }

    await fetchPendingItems();
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);
    alert(`Successfully approved ${successCount} out of ${selectedReviewItems.size} items`);
  };

  const bulkBlockSenders = async () => {
    if (selectedReviewItems.size === 0) {
      alert('Please select items to block senders');
      return;
    }

    // Get unique senders from selected items
    const sendersToBlock = new Set();
    selectedReviewItems.forEach(itemId => {
      const item = pendingReviewItems.find(i => i.id === itemId);
      if (item?.email_from) {
        sendersToBlock.add(item.email_from);
      }
    });

    if (!window.confirm(`Block ${sendersToBlock.size} sender(s) and delete ${selectedReviewItems.size} item(s)?\n\nBlocked senders:\n${Array.from(sendersToBlock).join('\n')}\n\nFuture emails from these senders will be automatically ignored.`)) {
      return;
    }

    setBulkProcessing(true);
    let successCount = 0;

    // Block each sender
    for (const sender of sendersToBlock) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/reconciliation/block-sender`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ sender_email: sender })
        });
      } catch (error) {
        console.error(`Error blocking sender ${sender}:`, error);
      }
    }

    // Delete the selected items
    for (const itemId of selectedReviewItems) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/reconciliation/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            extracted_data_id: itemId,
            reason: 'Sender blocked by user'
          })
        });

        if (response.ok) {
          successCount++;
        }
      } catch (error) {
        console.error(`Error deleting item ${itemId}:`, error);
      }
    }

    await fetchPendingItems();
    setSelectedReviewItems(new Set());
    setBulkProcessing(false);
    alert(`Blocked ${sendersToBlock.size} sender(s) and deleted ${successCount} items`);
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.85) return '#10b981'; // green
    if (confidence >= 0.65) return '#f59e0b'; // orange
    return '#ef4444'; // red
  };

  const getConfidenceBadge = (confidence) => {
    if (confidence >= 0.85) return 'HIGH';
    if (confidence >= 0.65) return 'MEDIUM';
    return 'LOW';
  };

  const formatFieldName = (fieldName) => {
    return fieldName
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const extractNameFromEmail = (email) => {
    // Extract name from email address (e.g., robert.w@example.com -> Robert W)
    if (!email) return 'Unknown';
    const namePart = email.split('@')[0];
    return namePart
      .split('.')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  };

  const formatFieldValue = (fieldName, value) => {
    if (!value) return 'N/A';

    if (fieldName.includes('date')) {
      try {
        return new Date(value).toLocaleDateString();
      } catch {
        return value;
      }
    }

    if (fieldName === 'loan_amount' || fieldName === 'appraisal_value') {
      return `$${parseFloat(value).toLocaleString()}`;
    }

    if (fieldName === 'rate') {
      return `${value}%`;
    }

    return value;
  };

  if (loading) {
    return (
      <div className="reconciliation-page">
        <div className="reconciliation-container">
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading reconciliation items...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="reconciliation-page">
      <div className="reconciliation-container">
        <div className="reconciliation-header">
          <div className="header-content">
            <h1>Data Reconciliation Center</h1>
            <p>Review and approve AI-extracted loan data from emails</p>

            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                className={`tab-button ${activeTab === 'pending' ? 'active' : ''}`}
                onClick={() => setActiveTab('pending')}
              >
                Auto-Processing ({pendingItems.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'pendingReview' ? 'active' : ''}`}
                onClick={() => setActiveTab('pendingReview')}
              >
                Pending Review ({pendingReviewItems.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'completed' ? 'active' : ''}`}
                onClick={() => setActiveTab('completed')}
              >
                Completed ({completedItems.length})
              </button>
            </div>
          </div>
          <div className="header-actions">
            <button
              className={`sync-button ${syncingEmails ? 'syncing' : ''}`}
              onClick={() => syncEmails(false)}
              disabled={syncingEmails}
            >
              {syncingEmails ? (
                <>
                  <span className="spinner-small"></span>
                  Syncing...
                </>
              ) : (
                <>
                  <span className="sync-icon">⟳</span>
                  Sync Emails Now
                </>
              )}
            </button>
            {syncStatus && (
              <div className={`sync-status ${syncStatus.includes('✓') ? 'success' : 'error'}`}>
                {syncStatus}
              </div>
            )}
            {lastSyncTime && !syncStatus && (
              <div className="last-sync">
                Last synced: {lastSyncTime.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

        {/* Bulk Actions Bar - only show for pending tab */}
        {activeTab === 'pending' && pendingItems.length > 0 && (
          <div className="bulk-actions-bar">
            <div className="bulk-controls">
              <button
                className="btn-select-all"
                onClick={selectAll}
                disabled={pendingItems.length === 0}
              >
                Select All (20)
              </button>
              <button
                className="btn-deselect"
                onClick={deselectAll}
                disabled={selectedItems.size === 0}
              >
                Deselect All
              </button>
              <span className="selection-count">
                {selectedItems.size} item{selectedItems.size !== 1 ? 's' : ''} selected
              </span>
            </div>
            <div className="bulk-buttons">
              <button
                className="btn-bulk-approve"
                onClick={bulkApprove}
                disabled={selectedItems.size === 0 || bulkProcessing}
              >
                {bulkProcessing ? (
                  <>
                    <span className="spinner-small"></span>
                    Processing...
                  </>
                ) : (
                  <>
                    ✓ Approve Selected ({selectedItems.size})
                  </>
                )}
              </button>
              <button
                className="btn-bulk-reject"
                onClick={bulkReject}
                disabled={selectedItems.size === 0 || bulkProcessing}
              >
                ✕ Reject Selected
              </button>
            </div>
          </div>
        )}

        {/* Pending Tab Content */}
        {activeTab === 'pending' && pendingItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✓</div>
            <h2>All Caught Up!</h2>
            <p>No pending reconciliation items. The AI will notify you when new data arrives.</p>
          </div>
        ) : activeTab === 'pending' && pendingItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Items List */}
            <div className="items-list">
              {pendingItems.slice(0, 20).map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${selectedItems.has(item.id) ? 'checked' : ''}`}
                >
                  <div className="item-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedItems.has(item.id)}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleItemSelection(item.id);
                      }}
                      disabled={!selectedItems.has(item.id) && selectedItems.size >= 20}
                    />
                  </div>
                  <div className="item-content" onClick={() => setSelectedItem(item)}>
                    <div className="item-header">
                      <div className="item-category">
                        {item.category?.toUpperCase() || 'UNKNOWN'}
                      </div>
                      <div
                        className="confidence-badge"
                        style={{ backgroundColor: getConfidenceColor(item.ai_confidence) }}
                      >
                        {getConfidenceBadge(item.ai_confidence)}
                      </div>
                    </div>
                  <div className="item-subject">{item.email?.subject}</div>
                  <div className="item-meta">
                    <span className="meta-sender">From: {item.email?.sender}</span>
                    <span className="meta-date">
                      {new Date(item.email?.received_at).toLocaleDateString()}
                    </span>
                  </div>
                  {item.match_entity_type && (
                    <div className="item-match">
                      Matched to: {item.match_entity_type} #{item.match_entity_id} (
                      {Math.round(item.match_confidence * 100)}%)
                    </div>
                  )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel */}
            {selectedItem && (
              <div className="detail-panel">
                <div className="panel-header">
                  <h2>Review Extracted Data</h2>
                  <button
                    className="close-panel"
                    onClick={() => {
                      setSelectedItem(null);
                      setEditedFields({});
                    }}
                  >
                    ✕
                  </button>
                </div>

                <div className="email-context">
                  <h3>Email Context</h3>
                  <div className="context-field">
                    <strong>Subject:</strong> {selectedItem.email?.subject}
                  </div>
                  <div className="context-field">
                    <strong>From:</strong> {selectedItem.email?.sender}
                  </div>
                  <div className="context-field">
                    <strong>Received:</strong>{' '}
                    {new Date(selectedItem.email?.received_at).toLocaleString()}
                  </div>
                </div>

                {/* Entity Match Info */}
                {selectedItem.match_entity_type && selectedItem.match_entity_id && (
                  <div className="entity-match-section">
                    <h3>Matched Profile</h3>
                    <div className="entity-match-card">
                      <div className="entity-icon">
                        {selectedItem.match_entity_type === 'lead' ? '👤' :
                         selectedItem.match_entity_type === 'active_loan' ? '🏠' :
                         selectedItem.match_entity_type === 'client' ? '👥' : '📋'}
                      </div>
                      <div className="entity-details">
                        <div className="entity-name">
                          {selectedItem.match_entity_name || `${selectedItem.match_entity_type} #${selectedItem.match_entity_id}`}
                        </div>
                        <div className="entity-type">
                          {selectedItem.match_entity_type === 'active_loan' ? 'Active Loan' :
                           selectedItem.match_entity_type === 'lead' ? 'Lead' :
                           selectedItem.match_entity_type === 'client' ? 'Client' :
                           selectedItem.match_entity_type}
                        </div>
                        <div className="entity-confidence">
                          Match Confidence: {Math.round(selectedItem.match_confidence * 100)}%
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Email Intent Classification */}
                {selectedItem.email_intent && (
                  <div className="email-intent-section">
                    <h3>Email Type Detected</h3>
                    <div className="intent-card">
                      <div className="intent-badge">
                        {selectedItem.email_intent}
                      </div>
                      {selectedItem.email_intent_description && (
                        <div className="intent-description">
                          {selectedItem.email_intent_description}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Recommended Action */}
                {selectedItem.recommended_action && (
                  <div className="recommended-action-section">
                    <h3>AI Recommendation</h3>
                    <div className="recommendation-card">
                      <div className="recommendation-icon">💡</div>
                      <div className="recommendation-content">
                        <div className="recommendation-title">
                          {selectedItem.recommended_action.title || 'Suggested Action'}
                        </div>
                        <div className="recommendation-description">
                          {selectedItem.recommended_action.description}
                        </div>
                        {selectedItem.recommended_action.learning_status && (
                          <div className="learning-status">
                            🧠 AI Learning: {selectedItem.recommended_action.learning_status}
                          </div>
                        )}
                        <div className="ai-delegation-option">
                          <label className="delegation-checkbox">
                            <input
                              type="checkbox"
                              checked={delegateToAI}
                              onChange={(e) => setDelegateToAI(e.target.checked)}
                            />
                            <span className="delegation-label">
                              ✓ Let AI handle this task type automatically in the future
                            </span>
                          </label>
                          {delegateToAI && (
                            <div className="delegation-notice">
                              When you approve, AI will automatically handle "{selectedItem.email_intent}" emails going forward. You can revoke this in Mission Control.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="extracted-fields">
                  <h3>Extracted Fields</h3>
                  <div className="fields-grid">
                    {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                      const confidence = fieldData.confidence || 0;
                      const value = fieldData.value;
                      const isEdited = fieldName in editedFields;
                      const displayValue = isEdited
                        ? editedFields[fieldName]
                        : formatFieldValue(fieldName, value);

                      return (
                        <div key={fieldName} className="field-row">
                          <div className="field-label">
                            <span>{formatFieldName(fieldName)}</span>
                            <span
                              className="field-confidence"
                              style={{ color: getConfidenceColor(confidence) }}
                            >
                              {Math.round(confidence * 100)}%
                            </span>
                          </div>
                          <input
                            type="text"
                            className={`field-input ${isEdited ? 'edited' : ''}`}
                            value={isEdited ? editedFields[fieldName] : value || ''}
                            onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>

                {Object.keys(editedFields).length > 0 && (
                  <div className="corrections-notice">
                    <strong>Note:</strong> {Object.keys(editedFields).length} field(s) edited.
                    The AI will learn from your corrections.
                  </div>
                )}

                <div className="action-buttons">
                  <button
                    className="btn-approve"
                    onClick={() => handleApprove(selectedItem.id)}
                    disabled={processingAction}
                  >
                    {processingAction ? 'Processing...' : 'Approve & Apply'}
                  </button>
                  <button
                    className="btn-reject"
                    onClick={() => {
                      const reason = prompt('Reason for rejection (optional):');
                      if (reason !== null) {
                        handleReject(selectedItem.id, reason);
                      }
                    }}
                    disabled={processingAction}
                  >
                    Reject
                  </button>
                </div>

                <div className="ai-info">
                  <div className="info-row">
                    <strong>AI Confidence:</strong>
                    <span style={{ color: getConfidenceColor(selectedItem.ai_confidence) }}>
                      {Math.round(selectedItem.ai_confidence * 100)}%
                    </span>
                  </div>
                  {selectedItem.match_entity_type && (
                    <div className="info-row">
                      <strong>Entity Match:</strong>
                      <span>
                        {selectedItem.match_entity_type} #{selectedItem.match_entity_id} (
                        {Math.round(selectedItem.match_confidence * 100)}%)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Pending Review Tab Content */}
        {activeTab === 'pendingReview' && pendingReviewItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✓</div>
            <h2>All Reviewed!</h2>
            <p>No items pending review. Items flagged by AI for manual review will appear here.</p>
          </div>
        ) : null}

        {/* Bulk Actions Bar for Pending Review - Outside reconciliation-content */}
        {activeTab === 'pendingReview' && pendingReviewItems.length > 0 && (
          <div className="bulk-actions-bar">
            <div className="selection-controls">
              <button
                className="select-btn"
                onClick={selectedReviewItems.size === pendingReviewItems.length ? deselectAllReviewItems : selectAllReviewItems}
              >
                {selectedReviewItems.size === pendingReviewItems.length ? '☐ Deselect All' : '☑ Select All'}
              </button>
              <span className="selection-count">
                {selectedReviewItems.size} of {pendingReviewItems.length} selected
              </span>
            </div>
            <div className="bulk-action-buttons">
              <button
                className="btn-success"
                onClick={bulkApproveReviewItems}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                ✓ Approve ({selectedReviewItems.size})
              </button>
              <button
                className="btn-warning"
                onClick={bulkBlockSenders}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                🚫 Block Sender ({selectedReviewItems.size})
              </button>
              <button
                className="btn-danger"
                onClick={bulkDeleteReviewItems}
                disabled={selectedReviewItems.size === 0 || bulkProcessing}
              >
                🗑️ Delete ({selectedReviewItems.size})
              </button>
            </div>
          </div>
        )}

        {activeTab === 'pendingReview' && pendingReviewItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Pending Review Items List */}
            <div className="items-list">
              {/* Select All Header */}
              <div className="select-all-header">
                <input
                  type="checkbox"
                  className="item-checkbox"
                  checked={selectedReviewItems.size === pendingReviewItems.length && pendingReviewItems.length > 0}
                  onChange={() => {
                    if (selectedReviewItems.size === pendingReviewItems.length) {
                      deselectAllReviewItems();
                    } else {
                      selectAllReviewItems();
                    }
                  }}
                />
                <span className="select-all-label">
                  {selectedReviewItems.size === pendingReviewItems.length ? 'Deselect All' : 'Select All'} ({pendingReviewItems.length} items)
                </span>
              </div>
              {pendingReviewItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${selectedReviewItems.has(item.id) ? 'checked' : ''}`}
                  onClick={() => setSelectedItem(item)}
                >
                  <input
                    type="checkbox"
                    className="item-checkbox"
                    checked={selectedReviewItems.has(item.id)}
                    onChange={() => toggleReviewItemSelection(item.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">
                        {item.email_intent || 'UNKNOWN'}
                      </div>
                      <div className="status-badge warning">
                        ⚠️ NEEDS REVIEW
                      </div>
                    </div>
                    <div className="item-subject">{item.email_subject}</div>
                    <div className="item-meta">
                      <span className="item-from">From: {item.email_from}</span>
                      <span className="item-date">
                        {new Date(item.email_received_at).toLocaleDateString()}
                      </span>
                    </div>
                    {item.email_body && (
                      <div className="item-body-preview">
                        {item.email_body.substring(0, 150)}{item.email_body.length > 150 ? '...' : ''}
                      </div>
                    )}
                    {item.review_reason && (
                      <div className="review-reason">
                        <strong>Reason:</strong> {item.review_reason}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel for Pending Review - Matches Task Detail Layout */}
            {selectedItem && (
              <div className="item-detail-panel">
                <div className="detail-header">
                  <div className="detail-title-section">
                    <div className="detail-source">
                      <span className="source-icon-large">🎯</span>
                      <span className="source-name">MANUAL PRIORITY</span>
                    </div>
                    <h2 className="detail-title">{selectedItem.email_intent || 'Review Required'}</h2>
                  </div>
                  <button className="close-detail" onClick={() => setSelectedItem(null)}>×</button>
                </div>

                <div className="detail-body">
                  <div className="detail-info-grid">
                    <div className="detail-info-item">
                      <span className="detail-label">CLIENT</span>
                      <span className="detail-value">{selectedItem.fields?.borrower_name?.value || extractNameFromEmail(selectedItem.email_from)}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">STAGE</span>
                      <span className="detail-value">{selectedItem.match_entity_type === 'lead' ? 'Pre-Approved' : selectedItem.match_entity_type === 'loan' ? 'Processing' : 'Client Retention'}</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">PRIORITY</span>
                      <span className="detail-urgency-badge priority-high">HIGH</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">SOURCE</span>
                      <span className="detail-value">Manual Priority</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">OWNER</span>
                      <span className="detail-value">Loan Officer</span>
                    </div>
                    <div className="detail-info-item">
                      <span className="detail-label">DATE CREATED</span>
                      <span className="detail-value">
                        {new Date(selectedItem.email_received_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="detail-info-item detail-comm-method-item">
                      <span className="detail-label">SEND VIA</span>
                      <div className="comm-method-selector">
                        <button className="comm-method-btn active">
                          📧 Email
                        </button>
                        <button className="comm-method-btn">
                          💬 Text
                        </button>
                        <button className="comm-method-btn">
                          📞 Phone
                        </button>
                        <button className="comm-method-btn">
                          🎙️ Voicemail
                        </button>
                      </div>
                    </div>
                  </div>

                  {selectedItem.review_reason && (
                    <div className="review-alert-banner">
                      <div className="alert-icon">⚠️</div>
                      <div className="alert-content">
                        <strong>Flagged for Review:</strong> {selectedItem.review_reason}
                        <br />
                        <span className="match-confidence-text">
                          Match Confidence: <strong>{Math.round(selectedItem.match_confidence * 100)}%</strong>
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Entity Match Section with Extracted Fields */}
                  <div className="extracted-fields-section">
                    <h3>Matched Entity</h3>
                    <div className="entity-match-info">
                      <div className="entity-type-badge">
                        {selectedItem.match_entity_type === 'lead' ? 'Lead' :
                         selectedItem.match_entity_type === 'loan' ? 'Loan' :
                         selectedItem.match_entity_type === 'client' ? 'Client' :
                         selectedItem.match_entity_type}
                      </div>
                      <div className="entity-confidence">
                        Match Confidence: <span style={{ color: getConfidenceColor(selectedItem.match_confidence) }}>
                          {Math.round(selectedItem.match_confidence * 100)}%
                        </span>
                      </div>
                    </div>
                    <h4>EXTRACTED FIELDS</h4>
                    <div className="fields-grid-recon">
                      {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                        const confidence = fieldData.confidence || 0;
                        const value = fieldData.value;
                        const isEdited = fieldName in editedFields;

                        return (
                          <div key={fieldName} className="field-row-recon">
                            <div className="field-header-recon">
                              <span className="field-name">{formatFieldName(fieldName)}</span>
                              <span
                                className="field-confidence-badge"
                                style={{
                                  backgroundColor: confidence > 0.8 ? '#10b981' : confidence > 0.6 ? '#f59e0b' : '#ef4444',
                                  color: 'white'
                                }}
                              >
                                {Math.round(confidence * 100)}%
                              </span>
                            </div>
                            <div className="field-value-display">{value || 'N/A'}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Email Details Section */}
                  <div className="email-details-section">
                    <button
                      className="history-accordion-button"
                      onClick={() => {}}
                    >
                      <span className="history-icon">📧</span>
                      <span className="history-title">Email Details</span>
                      <span className="history-toggle">▼</span>
                    </button>
                    <div className="email-details-content">
                      <div className="email-meta-row">
                        <strong>From:</strong> {selectedItem.email_from}
                      </div>
                      <div className="email-meta-row">
                        <strong>Subject:</strong> {selectedItem.email_subject}
                      </div>
                      <div className="email-meta-row">
                        <strong>Received:</strong> {new Date(selectedItem.email_received_at).toLocaleString()}
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons - Match Task Layout */}
                  <div className="detail-action-buttons">
                    <button
                      className="btn-approve-recon"
                      onClick={() => handleApprove(selectedItem.id)}
                      disabled={processingAction}
                    >
                      {processingAction ? 'Processing...' : '✓ APPROVE & CONTINUE'}
                    </button>
                    <button
                      className="btn-reject-recon"
                      onClick={() => {
                        const reason = prompt('Reason for rejection (optional):');
                        if (reason !== null) {
                          handleReject(selectedItem.id, reason);
                        }
                      }}
                      disabled={processingAction}
                    >
                      ✕ REJECT
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Completed Tab Content */}
        {activeTab === 'completed' && completedItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h2>No Completed Items</h2>
            <p>Approved and rejected reconciliation items will appear here.</p>
          </div>
        ) : activeTab === 'completed' && completedItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Completed Items List */}
            <div className="items-list">
              {completedItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.status === 'rejected' ? 'rejected-item' : 'approved-item'}`}
                  onClick={() => setSelectedItem(item)}
                >
                  <div className="item-content">
                    <div className="item-header">
                      <div className="item-category">
                        {item.category?.toUpperCase() || 'UNKNOWN'}
                      </div>
                      <div className={`status-badge ${item.status === 'rejected' ? 'rejected' : 'approved'}`}>
                        {item.status === 'rejected' ? '✕ REJECTED' : '✓ APPROVED'}
                      </div>
                    </div>
                    <div className="item-subject">{item.email?.subject}</div>
                    <div className="item-meta">
                      <span className="meta-sender">From: {item.email?.sender}</span>
                      <span className="meta-date">
                        Reviewed: {item.reviewed_at ? new Date(item.reviewed_at).toLocaleDateString() : 'N/A'}
                      </span>
                      {item.reviewed_by && (
                        <span className="meta-reviewer">By: {item.reviewed_by}</span>
                      )}
                    </div>
                    {item.match_entity_type && (
                      <div className="item-match">
                        Applied to: {item.match_entity_type} #{item.match_entity_id}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel for Completed Items - Read Only */}
            {selectedItem && (
              <div className="detail-panel">
                <div className="panel-header">
                  <h2>Completed Item Details</h2>
                  <button
                    className="close-panel"
                    onClick={() => setSelectedItem(null)}
                  >
                    ✕
                  </button>
                </div>

                <div className="email-context">
                  <h3>Email Context</h3>
                  <div className="context-field">
                    <strong>Subject:</strong> {selectedItem.email?.subject}
                  </div>
                  <div className="context-field">
                    <strong>From:</strong> {selectedItem.email?.sender}
                  </div>
                  <div className="context-field">
                    <strong>Received:</strong>{' '}
                    {new Date(selectedItem.email?.received_at).toLocaleString()}
                  </div>
                  <div className="context-field">
                    <strong>Status:</strong>{' '}
                    <span className={`status-text ${selectedItem.status}`}>
                      {selectedItem.status?.toUpperCase()}
                    </span>
                  </div>
                  {selectedItem.reviewed_at && (
                    <div className="context-field">
                      <strong>Reviewed:</strong>{' '}
                      {new Date(selectedItem.reviewed_at).toLocaleString()}
                      {selectedItem.reviewed_by && ` by ${selectedItem.reviewed_by}`}
                    </div>
                  )}
                </div>

                <div className="extracted-fields">
                  <h3>Extracted Fields (Read-Only)</h3>
                  <div className="fields-grid">
                    {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
                      const confidence = fieldData.confidence || 0;
                      const value = fieldData.value;

                      return (
                        <div key={fieldName} className="field-row">
                          <div className="field-label">
                            <span>{formatFieldName(fieldName)}</span>
                            <span
                              className="field-confidence"
                              style={{ color: getConfidenceColor(confidence) }}
                            >
                              {Math.round(confidence * 100)}%
                            </span>
                          </div>
                          <input
                            type="text"
                            className="field-input"
                            value={value || ''}
                            readOnly
                            disabled
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="ai-info">
                  <div className="info-row">
                    <strong>AI Confidence:</strong>
                    <span style={{ color: getConfidenceColor(selectedItem.ai_confidence) }}>
                      {Math.round(selectedItem.ai_confidence * 100)}%
                    </span>
                  </div>
                  {selectedItem.match_entity_type && (
                    <div className="info-row">
                      <strong>Entity Match:</strong>
                      <span>
                        {selectedItem.match_entity_type} #{selectedItem.match_entity_id} (
                        {Math.round(selectedItem.match_confidence * 100)}%)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default ReconciliationCenter;
