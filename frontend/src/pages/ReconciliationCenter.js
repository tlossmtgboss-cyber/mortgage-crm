import React, { useState, useEffect } from 'react';
import './ReconciliationCenter.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function ReconciliationCenter() {
  const [pendingItems, setPendingItems] = useState([]);
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

  useEffect(() => {
    fetchPendingItems();

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
        setPendingItems(data.items || []);
      }
    } catch (error) {
      console.error('Error fetching pending items:', error);
    } finally {
      setLoading(false);
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
          // Refresh pending items to show new data
          fetchPendingItems();

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
          corrections: corrections
        })
      });

      if (response.ok) {
        // Remove from list and reset
        setPendingItems(prev => prev.filter(item => item.id !== itemId));
        setSelectedItem(null);
        setEditedFields({});
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

        {/* Bulk Actions Bar */}
        {pendingItems.length > 0 && (
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

        {pendingItems.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✓</div>
            <h2>All Caught Up!</h2>
            <p>No pending reconciliation items. The AI will notify you when new data arrives.</p>
          </div>
        ) : (
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
        )}
      </div>
    </div>
  );
}

export default ReconciliationCenter;
