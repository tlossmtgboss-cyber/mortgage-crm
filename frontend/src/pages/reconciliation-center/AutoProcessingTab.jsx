import React from 'react';
import { FIELD_TYPE_OPTIONS } from './constants';
import { getConfidenceColor, getConfidenceBadge, formatFieldName, formatDisplayValue } from './helpers';

/**
 * AutoProcessingTab - Shows items AI is handling automatically.
 * Uses the legacy detail panel layout with extracted fields.
 */
export default function AutoProcessingTab({
  autoProcessingItems,
  pendingItems,
  selectedItem,
  selectedItems,
  handleSelectItem,
  toggleItemSelection,
  selectAll,
  deselectAll,
  bulkApprove,
  bulkReject,
  bulkProcessing,
  handleApprove,
  handleReject,
  processingAction,
  // Field editing
  editedFields,
  deletedFields,
  renamedFields,
  editingFieldKey,
  handleFieldEdit,
  handleFieldDelete,
  handleFieldRestore,
  handleFieldRename,
  handleFieldRenameUndo,
  setEditingFieldKey,
  getEffectiveFieldKey,
  setSelectedItem,
  setEditedFields,
  // AI delegation
  delegateToAI,
  setDelegateToAI,
}) {
  if (autoProcessingItems.length === 0) {
    return (
      <>
        {/* Bulk Actions Bar */}
        {autoProcessingItems.length > 0 && (
          <BulkActionsBar
            autoProcessingItems={autoProcessingItems}
            selectedItems={selectedItems}
            selectAll={selectAll}
            deselectAll={deselectAll}
            bulkApprove={bulkApprove}
            bulkReject={bulkReject}
            bulkProcessing={bulkProcessing}
          />
        )}
        <div className="empty-state">
          <div className="empty-icon"></div>
          <h2>No Auto-Processing Items</h2>
          <p>Messages that AI handles automatically will appear here. Enable auto-processing by checking the box when approving similar messages.</p>
        </div>
      </>
    );
  }

  return (
    <>
      {/* Bulk Actions Bar */}
      <BulkActionsBar
        autoProcessingItems={autoProcessingItems}
        selectedItems={selectedItems}
        selectAll={selectAll}
        deselectAll={deselectAll}
        bulkApprove={bulkApprove}
        bulkReject={bulkReject}
        bulkProcessing={bulkProcessing}
      />

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
              <div className="item-content" onClick={() => handleSelectItem(item)}>
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
                <div className="item-date-display">
                  {new Date(item.email?.received_at).toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                  })}
                </div>
                <div className="item-meta">
                  <span className="meta-sender">{item.email?.sender}</span>
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
                &#10005;
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
                    {selectedItem.match_entity_type === 'lead' ? 'Lead' :
                     selectedItem.match_entity_type === 'active_loan' ? 'Loan' :
                     selectedItem.match_entity_type === 'client' ? 'Client' : 'Item'}
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
                  <div className="recommendation-icon"></div>
                  <div className="recommendation-content">
                    <div className="recommendation-title">
                      {selectedItem.recommended_action.title || 'Suggested Action'}
                    </div>
                    <div className="recommendation-description">
                      {selectedItem.recommended_action.description}
                    </div>
                    {selectedItem.recommended_action.learning_status && (
                      <div className="learning-status">
                        AI Learning: {selectedItem.recommended_action.learning_status}
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
                          Let AI handle this task type automatically in the future
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
                  const isDeleted = deletedFields.has(fieldName);
                  const isRenamed = fieldName in renamedFields;
                  const effectiveKey = getEffectiveFieldKey(fieldName);
                  const confidence = fieldData.confidence || 0;
                  const value = fieldData.value;
                  const isEdited = fieldName in editedFields;

                  if (isDeleted) {
                    return (
                      <div key={fieldName} className="field-row deleted" style={{ opacity: 0.5, background: '#fee2e2' }}>
                        <div className="field-label" style={{ textDecoration: 'line-through' }}>
                          <span>{formatFieldName(fieldName)}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ color: '#991b1b', fontSize: '12px' }}>Deleted</span>
                          <button
                            onClick={() => handleFieldRestore(fieldName)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '11px',
                              background: '#f3f4f6',
                              border: '1px solid #d1d5db',
                              borderRadius: '4px',
                              cursor: 'pointer'
                            }}
                            title="Restore field"
                          >
                            &#8617; Restore
                          </button>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div key={fieldName} className={`field-row ${isRenamed ? 'renamed' : ''}`}>
                      <div className="field-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {editingFieldKey === fieldName ? (
                          <select
                            value={effectiveKey}
                            onChange={(e) => handleFieldRename(fieldName, e.target.value)}
                            onBlur={() => setEditingFieldKey(null)}
                            autoFocus
                            style={{
                              padding: '4px 8px',
                              fontSize: '12px',
                              borderRadius: '4px',
                              border: '1px solid #3b82f6',
                              minWidth: '160px'
                            }}
                          >
                            <option value={fieldName}>{formatFieldName(fieldName)}</option>
                            {FIELD_TYPE_OPTIONS
                              .filter(opt => opt.value !== fieldName)
                              .map(opt => (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              ))}
                          </select>
                        ) : (
                          <>
                            <span
                              onClick={() => setEditingFieldKey(fieldName)}
                              style={{
                                cursor: 'pointer',
                                borderBottom: '1px dashed #9ca3af'
                              }}
                              title="Click to change field type"
                            >
                              {formatFieldName(effectiveKey)}
                            </span>
                            {isRenamed && (
                              <span style={{
                                fontSize: '10px',
                                color: '#2563eb',
                                background: '#dbeafe',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}>
                                was: {formatFieldName(fieldName)}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleFieldRenameUndo(fieldName);
                                  }}
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    fontSize: '10px',
                                    padding: '0 2px'
                                  }}
                                  title="Undo rename"
                                >
                                  &#10005;
                                </button>
                              </span>
                            )}
                          </>
                        )}
                        <span
                          className="field-confidence"
                          style={{ color: getConfidenceColor(confidence), marginLeft: 'auto' }}
                        >
                          {Math.round(confidence * 100)}%
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="text"
                          className={`field-input ${isEdited ? 'edited' : ''}`}
                          value={isEdited ? editedFields[fieldName] : formatDisplayValue(fieldName, value) || ''}
                          onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                          style={{ flex: 1 }}
                        />
                        <button
                          onClick={() => handleFieldDelete(fieldName)}
                          style={{
                            padding: '6px 10px',
                            background: '#fef2f2',
                            border: '1px solid #fecaca',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            color: '#dc2626',
                            fontSize: '14px'
                          }}
                          title="Delete field"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {(Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && (
              <div className="corrections-notice">
                <strong>Changes:</strong>{' '}
                {Object.keys(editedFields).length > 0 && `${Object.keys(editedFields).length} edited`}
                {Object.keys(editedFields).length > 0 && (deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
                {deletedFields.size > 0 && `${deletedFields.size} deleted`}
                {deletedFields.size > 0 && Object.keys(renamedFields).length > 0 && ', '}
                {Object.keys(renamedFields).length > 0 && `${Object.keys(renamedFields).length} renamed`}
                . The AI will learn from your corrections.
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
    </>
  );
}

function BulkActionsBar({ autoProcessingItems, selectedItems, selectAll, deselectAll, bulkApprove, bulkReject, bulkProcessing }) {
  if (autoProcessingItems.length === 0) return null;

  return (
    <div className="bulk-actions-bar">
      <div className="bulk-controls">
        <button
          className="btn-select-all"
          onClick={selectAll}
          disabled={autoProcessingItems.length === 0}
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
              Approve Selected ({selectedItems.size})
            </>
          )}
        </button>
        <button
          className="btn-bulk-reject"
          onClick={bulkReject}
          disabled={selectedItems.size === 0 || bulkProcessing}
        >
          Reject Selected
        </button>
      </div>
    </div>
  );
}
