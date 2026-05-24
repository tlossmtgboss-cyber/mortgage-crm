import React from 'react';
import { cleanEmailPreview, getConfidenceColor, extractNameFromEmail } from './helpers';
import EntityTypeSelector from './EntityTypeSelector';
import EditableFieldsGrid from './EditableFieldsGrid';

/**
 * PendingReviewTab - Items flagged by AI for manual review.
 * Includes bulk selection, detail panel with entity type selection,
 * editable fields, email body, and deploy/reject/delete actions.
 */
export default function PendingReviewTab({
  pendingReviewItems,
  selectedItem,
  selectedReviewItems,
  bulkProcessing,
  handleSelectItem,
  handleDelete,
  handleApprove,
  handleReject,
  processingAction,
  // Bulk actions
  toggleReviewItemSelection,
  selectAllReviewItems,
  deselectAllReviewItems,
  bulkDeleteReviewItems,
  bulkApproveReviewItems,
  bulkBlockSenders,
  // Entity type selection
  selectedEntityType,
  setSelectedEntityType,
  createNewLoan,
  setCreateNewLoan,
  selectedLoanStage,
  setSelectedLoanStage,
  // Field editing
  editedFields,
  deletedFields,
  renamedFields,
  addedFields,
  editingFieldKey,
  showAddFieldForm,
  newFieldKey,
  newFieldValue,
  handleFieldEdit,
  handleFieldDelete,
  handleFieldRestore,
  handleFieldRename,
  handleFieldRenameUndo,
  handleAddField,
  handleRemoveAddedField,
  setEditingFieldKey,
  setShowAddFieldForm,
  setNewFieldKey,
  setNewFieldValue,
  setAddedFields,
  getEffectiveFieldKey,
  // AI skip review
  allowAutoProcess,
  setAllowAutoProcess,
  // Close detail
  setSelectedItem,
}) {
  if (pendingReviewItems.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon"></div>
        <h2>All Reviewed!</h2>
        <p>No items pending review. Items flagged by AI for manual review will appear here.</p>
      </div>
    );
  }

  return (
    <>
      {/* Bulk Actions Bar */}
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
            Approve ({selectedReviewItems.size})
          </button>
          <button
            className="btn-warning"
            onClick={bulkBlockSenders}
            disabled={selectedReviewItems.size === 0 || bulkProcessing}
          >
            &#128683; Block Sender ({selectedReviewItems.size})
          </button>
          <button
            className="btn-danger"
            onClick={bulkDeleteReviewItems}
            disabled={selectedReviewItems.size === 0 || bulkProcessing}
          >
            Delete ({selectedReviewItems.size})
          </button>
        </div>
      </div>

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
              onClick={() => handleSelectItem(item)}
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
                    NEEDS REVIEW
                  </div>
                </div>
                <div className="item-subject">{item.email_subject}</div>
                <div className="item-date-display">
                  {new Date(item.email_received_at).toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                  })}
                </div>
                <div className="item-meta">
                  <span className="item-from">{item.email_from}</span>
                </div>
                {item.email_body && (
                  <div className="item-body-preview">
                    {(() => {
                      const cleaned = cleanEmailPreview(item.email_body);
                      return cleaned.length > 120 ? cleaned.substring(0, 120) + '...' : cleaned;
                    })()}
                  </div>
                )}
                {item.review_reason && (
                  <div className="review-reason">
                    <strong>Reason:</strong> {item.review_reason}
                  </div>
                )}
              </div>
              <button
                className="item-delete-btn"
                onClick={(e) => { e.stopPropagation(); handleDelete(item.id); }}
                title="Delete"
              >
                &#128465;&#65039;
              </button>
            </div>
          ))}
        </div>

        {/* Detail Panel for Pending Review */}
        {selectedItem && (
          <div className="item-detail-panel">
            <div className="detail-header">
              <div className="detail-title-section">
                <div className="detail-source">
                  <span className="source-name">MANUAL PRIORITY</span>
                </div>
                <h2 className="detail-title">{selectedItem.email_intent || 'Review Required'}</h2>
              </div>
              <button className="close-detail" onClick={() => setSelectedItem(null)}>&times;</button>
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
              </div>

              {selectedItem.review_reason && (
                <div className="review-alert-banner">
                  <div className="alert-icon"></div>
                  <div className="alert-content">
                    <strong>Flagged for Review:</strong> {selectedItem.review_reason}
                    <br />
                    <span className="match-confidence-text">
                      Match Confidence: <strong>{Math.round(selectedItem.match_confidence * 100)}%</strong>
                    </span>
                  </div>
                </div>
              )}

              <EntityTypeSelector
                selectedItem={selectedItem}
                selectedEntityType={selectedEntityType}
                setSelectedEntityType={setSelectedEntityType}
                createNewLoan={createNewLoan}
                setCreateNewLoan={setCreateNewLoan}
                selectedLoanStage={selectedLoanStage}
                setSelectedLoanStage={setSelectedLoanStage}
                showMumCategory={true}
                showOtherCategory={true}
              />

              {/* Entity Match Section with Extracted Fields */}
              <div className="extracted-fields-section">
                <h3>Matched Entity</h3>
                <div className="entity-match-info">
                  <div className="entity-type-badge" style={{
                    background: createNewLoan ? '#B8924A' :
                               (selectedEntityType || selectedItem.match_entity_type) === 'loan' ? '#3b82f6' :
                               '#2D7A52',
                    color: 'white',
                    padding: '4px 12px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: '500'
                  }}>
                    {createNewLoan ? 'New Loan' :
                     (selectedEntityType || selectedItem.match_entity_type) === 'lead' ? 'Lead' :
                     (selectedEntityType || selectedItem.match_entity_type) === 'loan' ? 'Loan' :
                     selectedItem.match_entity_type}
                  </div>
                  <div className="entity-confidence">
                    Match Confidence: <span style={{ color: getConfidenceColor(selectedItem.match_confidence) }}>
                      {createNewLoan ? 'N/A' : `${Math.round(selectedItem.match_confidence * 100)}%`}
                    </span>
                  </div>
                </div>

                {/* Use a custom header for EXTRACTED FIELDS instead of the default */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <h4 style={{ margin: 0 }}>EXTRACTED FIELDS</h4>
                  <button
                    onClick={() => setShowAddFieldForm(true)}
                    style={{
                      padding: '6px 12px',
                      fontSize: '12px',
                      background: '#2D7A52',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}
                  >
                    + Add Field
                  </button>
                </div>

                <EditableFieldsGrid
                  selectedItem={selectedItem}
                  editedFields={editedFields}
                  deletedFields={deletedFields}
                  renamedFields={renamedFields}
                  addedFields={addedFields}
                  editingFieldKey={editingFieldKey}
                  showAddFieldForm={showAddFieldForm}
                  newFieldKey={newFieldKey}
                  newFieldValue={newFieldValue}
                  handleFieldEdit={handleFieldEdit}
                  handleFieldDelete={handleFieldDelete}
                  handleFieldRestore={handleFieldRestore}
                  handleFieldRename={handleFieldRename}
                  handleFieldRenameUndo={handleFieldRenameUndo}
                  handleAddField={handleAddField}
                  handleRemoveAddedField={handleRemoveAddedField}
                  setEditingFieldKey={setEditingFieldKey}
                  setShowAddFieldForm={() => {}} // Already handled above
                  setNewFieldKey={setNewFieldKey}
                  setNewFieldValue={setNewFieldValue}
                  setAddedFields={setAddedFields}
                  getEffectiveFieldKey={getEffectiveFieldKey}
                />
              </div>

              {/* Email Details Section */}
              <div className="email-details-section">
                <h4>Email Details</h4>
                <div className="email-details-content" style={{ background: '#f9fafb', padding: '15px', borderRadius: '8px', marginTop: '10px' }}>
                  <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                    <strong>From:</strong> {selectedItem.email_from}
                  </div>
                  <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                    <strong>Subject:</strong> {selectedItem.email_subject}
                  </div>
                  <div className="email-meta-row" style={{ marginBottom: '8px' }}>
                    <strong>Received:</strong> {new Date(selectedItem.email_received_at).toLocaleString()}
                  </div>
                  <div className="email-body-section" style={{ marginTop: '15px', borderTop: '1px solid #e5e7eb', paddingTop: '15px' }}>
                    <strong>Email Body:</strong>
                    <div
                      className="email-body-content"
                      style={{
                        marginTop: '10px',
                        padding: '15px',
                        background: 'white',
                        border: '1px solid #e5e7eb',
                        borderRadius: '6px',
                        maxHeight: '400px',
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        fontFamily: 'monospace',
                        fontSize: '13px',
                        lineHeight: '1.5'
                      }}
                    >
                      {selectedItem.email_body || selectedItem.email?.body || selectedItem.email?.text_content || selectedItem.email?.html_content || 'No email body available'}
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Skip Review Checkbox */}
              <div className="ai-skip-review-section" style={{ marginTop: '20px', padding: '15px', background: '#ecfdf5', borderRadius: '8px', border: '1px solid #86efac' }}>
                <label className="skip-review-checkbox" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={allowAutoProcess}
                    onChange={(e) => setAllowAutoProcess(e.target.checked)}
                    style={{ marginTop: '3px' }}
                  />
                  <div>
                    <span style={{ fontWeight: '600', color: '#166534' }}>
                      Skip review for similar messages in the future
                    </span>
                    <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#15803d' }}>
                      When deployed, AI will automatically complete and deploy similar "{selectedItem.email_intent || 'email'}" messages without requiring your review.
                    </p>
                  </div>
                </label>
              </div>

              {/* Action Buttons */}
              <div className="detail-action-buttons">
                <button
                  className="btn-approve-recon"
                  onClick={() => handleApprove(selectedItem.id)}
                  disabled={processingAction}
                >
                  {processingAction ? 'Processing...' : 'DEPLOY'}
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
                  REJECT
                </button>
                <button
                  className="btn-delete-recon"
                  onClick={() => handleDelete(selectedItem.id)}
                  disabled={processingAction}
                >
                  &#128465;&#65039; DELETE
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
