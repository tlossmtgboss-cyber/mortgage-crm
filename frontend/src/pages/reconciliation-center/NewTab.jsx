import React from 'react';
import { cleanEmailPreview } from './helpers';
import EntityTypeSelector from './EntityTypeSelector';
import EditableFieldsGrid from './EditableFieldsGrid';

/**
 * NewTab - "New" tab content showing fresh unprocessed messages.
 * Left panel: item list. Right panel: detail view with entity type selection,
 * editable fields, email body, AI delegation, and action buttons.
 */
export default function NewTab({
  newItems,
  selectedItem,
  handleSelectItem,
  handleDelete,
  handleApprove,
  handleReject,
  processingAction,
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
  // AI delegation
  delegateToAI,
  setDelegateToAI,
  // Delete from inbox
  deleteFromInboxOverride,
  setDeleteFromInboxOverride,
  deleteFromInboxGlobal,
  // Close detail
  setSelectedItem,
}) {
  if (newItems.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon"></div>
        <h2>No New Messages</h2>
        <p>New emails will appear here for processing. Click "Sync Emails Now" to check for new messages.</p>
      </div>
    );
  }

  return (
    <div className="reconciliation-content">
      {/* New Items List */}
      <div className="items-list">
        {newItems.map((item) => (
          <div
            key={item.id}
            className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''}`}
            onClick={() => handleSelectItem(item)}
          >
            <div className="item-content">
              <div className="item-header">
                <div className="item-category">
                  {item.category?.toUpperCase() || item.email_intent || 'NEW'}
                </div>
                <div className="status-badge new-badge">
                  NEW
                </div>
              </div>
              <div className="item-subject">{item.email_subject || item.email?.subject}</div>
              <div className="item-date-display">
                {new Date(item.email_received_at || item.email?.received_at).toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                  hour12: true
                })}
              </div>
              <div className="item-meta">
                <span className="meta-sender">{item.email_from || item.email?.sender}</span>
              </div>
              {item.email_body && (
                <div className="item-body-preview">
                  {(() => {
                    const cleaned = cleanEmailPreview(item.email_body);
                    return cleaned.length > 120 ? cleaned.substring(0, 120) + '...' : cleaned;
                  })()}
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

      {/* Detail Panel for New Items */}
      {selectedItem && (
        <div className="item-detail-panel">
          <div className="detail-header">
            <div className="detail-title-section">
              <div className="detail-source">
                <span className="source-name">NEW MESSAGE</span>
              </div>
              <h2 className="detail-title">{selectedItem.email_intent || 'New Email'}</h2>
            </div>
            <button className="close-detail" onClick={() => setSelectedItem(null)}>&times;</button>
          </div>

          <div className="detail-body">
            <div className="detail-info-grid">
              <div className="detail-info-item">
                <span className="detail-label">FROM</span>
                <span className="detail-value">{selectedItem.email_from || selectedItem.email?.sender}</span>
              </div>
              <div className="detail-info-item">
                <span className="detail-label">SUBJECT</span>
                <span className="detail-value">{selectedItem.email_subject || selectedItem.email?.subject}</span>
              </div>
              <div className="detail-info-item">
                <span className="detail-label">RECEIVED</span>
                <span className="detail-value">
                  {new Date(selectedItem.email_received_at || selectedItem.email?.received_at).toLocaleString()}
                </span>
              </div>
              <div className="detail-info-item">
                <span className="detail-label">STATUS</span>
                <span className="detail-value">Awaiting Processing</span>
              </div>
            </div>

            <EntityTypeSelector
              selectedItem={selectedItem}
              selectedEntityType={selectedEntityType}
              setSelectedEntityType={setSelectedEntityType}
              createNewLoan={createNewLoan}
              setCreateNewLoan={setCreateNewLoan}
              selectedLoanStage={selectedLoanStage}
              setSelectedLoanStage={setSelectedLoanStage}
            />

            {/* Extracted Fields - Editable */}
            <div className="extracted-fields-section">
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
                setShowAddFieldForm={setShowAddFieldForm}
                setNewFieldKey={setNewFieldKey}
                setNewFieldValue={setNewFieldValue}
                setAddedFields={setAddedFields}
                getEffectiveFieldKey={getEffectiveFieldKey}
              />
            </div>

            {/* Email Body */}
            <div className="email-details-section">
              <h4>Email Content</h4>
              <div className="email-details-content" style={{ background: '#f9fafb', padding: '15px', borderRadius: '8px', marginTop: '10px' }}>
                <div
                  className="email-body-content"
                  style={{
                    padding: '15px',
                    background: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    maxHeight: '300px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    fontFamily: 'monospace',
                    fontSize: '13px',
                    lineHeight: '1.5'
                  }}
                >
                  {selectedItem.email_body || selectedItem.email?.body || selectedItem.email?.text_content || 'No email body available'}
                </div>
              </div>
            </div>

            {/* AI Auto-Process Checkbox */}
            <div className="ai-delegation-section" style={{ marginTop: '20px', padding: '15px', background: '#fef3c7', borderRadius: '8px', border: '1px solid #fcd34d' }}>
              <label className="delegation-checkbox" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={delegateToAI}
                  onChange={(e) => setDelegateToAI(e.target.checked)}
                  style={{ marginTop: '3px' }}
                />
                <div>
                  <span style={{ fontWeight: '600', color: '#92400e' }}>
                    Let AI auto-process similar messages
                  </span>
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#78350f' }}>
                    When approved, AI will automatically handle similar "{selectedItem.email_intent || 'email'}" messages in the future without requiring your review.
                  </p>
                </div>
              </label>
            </div>

            {/* Delete from Inbox Option */}
            <div style={{
              marginTop: '12px',
              padding: '12px 16px',
              background: deleteFromInboxOverride === true || (deleteFromInboxOverride === null && deleteFromInboxGlobal) ? '#fef2f2' : '#f8fafc',
              borderRadius: '8px',
              border: `1px solid ${deleteFromInboxOverride === true || (deleteFromInboxOverride === null && deleteFromInboxGlobal) ? '#fecaca' : '#e2e8f0'}`
            }}>
              <label style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                cursor: 'pointer'
              }}>
                <input
                  type="checkbox"
                  checked={deleteFromInboxOverride !== null ? deleteFromInboxOverride : deleteFromInboxGlobal}
                  onChange={(e) => setDeleteFromInboxOverride(e.target.checked)}
                  style={{ marginTop: '3px' }}
                />
                <div>
                  <span style={{ fontWeight: '600', color: '#dc2626' }}>
                    Also delete from inbox
                  </span>
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: '#6b7280' }}>
                    Move this email to trash in your email inbox after processing.
                    {deleteFromInboxGlobal && deleteFromInboxOverride === null && (
                      <span style={{ color: '#2D7A52', fontStyle: 'italic' }}> (Enabled by default in Settings)</span>
                    )}
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
                {processingAction ? 'Processing...' : 'Process & Apply'}
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
                Reject
              </button>
              <button
                className="btn-delete-recon"
                onClick={() => handleDelete(selectedItem.id)}
                disabled={processingAction}
              >
                &#128465;&#65039; Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
