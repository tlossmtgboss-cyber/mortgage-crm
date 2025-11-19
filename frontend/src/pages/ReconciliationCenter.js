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
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [approvalProgress, setApprovalProgress] = useState({ approved: 0, total: 20 });
  const [delegateToAI, setDelegateToAI] = useState(false);

  useEffect(() => {
    fetchPendingItems();
    fetchCompletedItems();
    loadSampleData(); // Load sample data

    // Auto-sync emails every 5 minutes
    const syncInterval = setInterval(() => {
      syncEmails(true); // silent sync
    }, 5 * 60 * 1000); // 5 minutes

    // Initial sync on load
    syncEmails(true);

    return () => clearInterval(syncInterval);
  }, []);

  // Load sample data for demonstration
  const loadSampleData = () => {
    // Generate 20 completed reconciliations
    const sampleCompleted = Array.from({ length: 20 }, (_, i) => {
      const statuses = ['approved', 'rejected'];
      const status = i < 15 ? 'approved' : 'rejected';
      const intents = [
        'Rate Lock Request',
        'Document Submission',
        'Application Update',
        'Question About Process',
        'Closing Date Inquiry',
        'Income Verification',
        'Property Appraisal Update',
        'Title Document Request'
      ];
      const entityTypes = ['lead', 'loan', 'client'];

      return {
        id: `comp-${i + 1}`,
        email_subject: `${intents[i % intents.length]} - ${['John Smith', 'Sarah Johnson', 'Michael Brown', 'Emily Davis'][i % 4]}`,
        email_from: `${['john.smith', 'sarah.j', 'michael.b', 'emily.d'][i % 4]}@example.com`,
        email_received_at: new Date(Date.now() - (i + 1) * 86400000).toISOString(),
        status: status,
        reviewed_at: new Date(Date.now() - i * 3600000).toISOString(),
        reviewed_by: 'demo@example.com',
        email_intent: intents[i % intents.length],
        match_entity_type: entityTypes[i % 3],
        match_entity_id: `entity-${i + 1}`,
        match_confidence: 0.85 + (Math.random() * 0.15),
        fields: {
          loan_amount: { value: `$${(250000 + i * 15000).toLocaleString()}`, confidence: 0.95 },
          property_address: { value: `${100 + i} Main St, ${['San Francisco', 'Oakland', 'San Jose', 'Berkeley'][i % 4]}, CA`, confidence: 0.92 },
          loan_type: { value: ['Conventional', 'FHA', 'VA', 'Jumbo'][i % 4], confidence: 0.88 },
          rate: { value: `${(3.5 + (i % 10) * 0.1).toFixed(2)}%`, confidence: 0.90 }
        }
      };
    });

    // Generate 12 pending review items
    const samplePendingReview = Array.from({ length: 12 }, (_, i) => {
      const intents = [
        'Rate Lock Request',
        'Document Upload',
        'Application Question',
        'Closing Coordination',
        'Income Update',
        'Appraisal Status',
        'Title Question',
        'Refinance Inquiry'
      ];

      return {
        id: `review-${i + 1}`,
        email_subject: `${intents[i % intents.length]} - ${['Robert Wilson', 'Jennifer Lee', 'David Martinez', 'Lisa Anderson'][i % 4]}`,
        email_from: `${['robert.w', 'jennifer.l', 'david.m', 'lisa.a'][i % 4]}@example.com`,
        email_received_at: new Date(Date.now() - i * 7200000).toISOString(),
        status: 'pending_review',
        email_intent: intents[i % intents.length],
        match_entity_type: ['lead', 'loan', 'client'][i % 3],
        match_entity_id: `entity-review-${i + 1}`,
        match_confidence: 0.75 + (Math.random() * 0.20),
        needs_human_review: true,
        review_reason: i % 3 === 0 ? 'Low confidence match' : i % 3 === 1 ? 'Complex document' : 'Unusual request pattern',
        fields: {
          loan_amount: { value: `$${(300000 + i * 25000).toLocaleString()}`, confidence: 0.70 + (Math.random() * 0.20) },
          borrower_name: { value: ['Robert Wilson', 'Jennifer Lee', 'David Martinez', 'Lisa Anderson'][i % 4], confidence: 0.88 },
          property_type: { value: ['Single Family', 'Condo', 'Townhouse', 'Multi-Family'][i % 4], confidence: 0.82 },
          down_payment: { value: `${15 + (i % 5) * 5}%`, confidence: 0.75 }
        },
        recommended_action: {
          title: 'Review and Approve',
          description: 'AI suggests manual review due to ' + (i % 3 === 0 ? 'low confidence match' : i % 3 === 1 ? 'complex document structure' : 'unusual request pattern')
        }
      };
    });

    setCompletedItems(sampleCompleted);
    setPendingReviewItems(samplePendingReview);
  };

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
        setPendingItems(data.items || []);
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

      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-now`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setLastSyncTime(new Date());

        if (!silent) {
          setSyncStatus(`✓ Synced ${data.processed_count} emails successfully`);
          // Refresh both pending and completed items to show new data
          fetchPendingItems();
          fetchCompletedItems();

          // Clear status after 3 seconds
          setTimeout(() => setSyncStatus(''), 3000);
        }
      } else {
        if (!silent) {
          setSyncStatus('⚠ Sync failed - please try again');
          setTimeout(() => setSyncStatus(''), 3000);
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
        setSelectedItem(null);
        setEditedFields({});
        setDelegateToAI(false);
        // Refresh completed items to show the newly approved item
        fetchCompletedItems();
      } else {
        alert('Failed to approve item');
      }
    } catch (error) {
      console.error('Error approving item:', error);
      alert('Error approving item');
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
        setSelectedItem(null);
        setEditedFields({});
        // Refresh completed items to show the rejected item
        fetchCompletedItems();
      } else {
        alert('Failed to reject item');
      }
    } catch (error) {
      console.error('Error rejecting item:', error);
      alert('Error rejecting item');
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
          <div className="header-stats">
            <div className="stat-card">
              <div className="stat-value">{pendingItems.length}</div>
              <div className="stat-label">Pending Review</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{selectedItems.size}/20</div>
              <div className="stat-label">Selected</div>
            </div>
            <div className="stat-card progress-card">
              <div className="stat-value">{approvalProgress.approved}/{approvalProgress.total}</div>
              <div className="stat-label">Approved Today</div>
            </div>
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
        ) : activeTab === 'pendingReview' && pendingReviewItems.length > 0 ? (
          <div className="reconciliation-content">
            {/* Pending Review Items List */}
            <div className="items-list">
              {pendingReviewItems.map((item) => (
                <div
                  key={item.id}
                  className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''}`}
                  onClick={() => setSelectedItem(item)}
                >
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
                    {item.review_reason && (
                      <div className="review-reason">
                        <strong>Review Reason:</strong> {item.review_reason}
                      </div>
                    )}
                    <div className="item-confidence">
                      <span className="confidence-label">Match Confidence:</span>
                      <span className="confidence-value" style={{ color: getConfidenceColor(item.match_confidence) }}>
                        {Math.round(item.match_confidence * 100)}%
                      </span>
                    </div>
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
