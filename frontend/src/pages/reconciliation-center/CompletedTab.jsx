import React from 'react';
import { getConfidenceColor, formatFieldName, formatDisplayValue } from './helpers';

/**
 * CompletedTab - Read-only view of approved/rejected reconciliation items.
 */
export default function CompletedTab({
  completedItems,
  selectedItem,
  handleSelectItem,
  handleDelete,
  setSelectedItem,
}) {
  if (completedItems.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon"></div>
        <h2>No Completed Items</h2>
        <p>Approved and rejected reconciliation items will appear here.</p>
      </div>
    );
  }

  return (
    <div className="reconciliation-content">
      {/* Completed Items List */}
      <div className="items-list">
        {completedItems.map((item) => (
          <div
            key={item.id}
            className={`reconciliation-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.status === 'rejected' ? 'rejected-item' : 'approved-item'}`}
            onClick={() => handleSelectItem(item)}
          >
            <div className="item-content">
              <div className="item-header">
                <div className="item-category">
                  {item.category?.toUpperCase() || 'UNKNOWN'}
                </div>
                <div className={`status-badge ${item.status === 'rejected' ? 'rejected' : 'approved'}`}>
                  {item.status === 'rejected' ? 'REJECTED' : 'APPROVED'}
                </div>
              </div>
              <div className="item-subject">{item.email?.subject}</div>
              <div className="item-date-display">
                {item.email?.received_at ? new Date(item.email.received_at).toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                  hour12: true
                }) : 'N/A'}
              </div>
              <div className="item-meta">
                <span className="meta-sender">{item.email?.sender}</span>
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

      {/* Detail Panel for Completed Items - Read Only */}
      {selectedItem && (
        <div className="detail-panel">
          <div className="panel-header">
            <h2>Completed Item Details</h2>
            <button
              className="close-panel"
              onClick={() => setSelectedItem(null)}
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
                      value={formatDisplayValue(fieldName, value) || ''}
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
  );
}
