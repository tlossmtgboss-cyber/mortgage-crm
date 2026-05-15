/**
 * Review & Approve Modal Component
 *
 * Modal for batch reviewing and approving artifacts from call analysis.
 */

import React, { useState, useMemo } from 'react';

const ReviewApproveModal = ({ artifacts, onSubmit, onClose }) => {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectAll, setSelectAll] = useState(false);

  // Filter to only pending artifacts
  const pendingArtifacts = useMemo(() => {
    return artifacts?.filter(a => a.approval_status === 'pending') || [];
  }, [artifacts]);

  // Group by type
  const groupedArtifacts = useMemo(() => {
    return pendingArtifacts.reduce((acc, artifact) => {
      const type = artifact.artifact_type;
      if (!acc[type]) {
        acc[type] = [];
      }
      acc[type].push(artifact);
      return acc;
    }, {});
  }, [pendingArtifacts]);

  const handleToggle = (id) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
    setSelectAll(newSelected.size === pendingArtifacts.length);
  };

  const handleSelectAll = () => {
    if (selectAll) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(pendingArtifacts.map(a => a.id)));
    }
    setSelectAll(!selectAll);
  };

  const handleSubmit = () => {
    onSubmit(Array.from(selectedIds));
  };

  const getTypeLabel = (type) => {
    const labels = {
      task: 'Tasks',
      action_item: 'Action Items',
      document_request: 'Document Requests',
      intake_field: '1003 Field Updates',
      risk_flag: 'Risk Flags',
      condition: 'Conditions',
      uw_note: 'UW Notes',
      summary: 'Summary',
      follow_up_draft: 'Follow-up Drafts',
    };
    return labels[type] || type;
  };

  const getTypeIcon = (type) => {
    const icons = {
      task: '✓',
      action_item: '→',
      document_request: '📄',
      intake_field: '📝',
      risk_flag: '⚠️',
      condition: '📋',
      uw_note: '📌',
    };
    return icons[type] || '•';
  };

  if (pendingArtifacts.length === 0) {
    return (
      <div className="review-modal-overlay" onClick={onClose}>
        <div className="review-modal" onClick={e => e.stopPropagation()}>
          <div className="review-modal-header">
            <h3>Review & Approve</h3>
            <button className="review-modal-close" onClick={onClose}>&times;</button>
          </div>
          <div className="review-modal-body" style={{ textAlign: 'center', padding: '40px' }}>
            <p style={{ color: '#6b7280' }}>No pending items to review.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="review-modal-overlay" onClick={onClose}>
      <div className="review-modal" onClick={e => e.stopPropagation()}>
        <div className="review-modal-header">
          <h3>Review & Approve ({pendingArtifacts.length} items)</h3>
          <button className="review-modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="review-modal-body">
          {/* Select All */}
          <div style={{
            padding: '12px',
            background: '#f9fafb',
            borderRadius: '8px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}>
            <input
              type="checkbox"
              id="selectAll"
              checked={selectAll}
              onChange={handleSelectAll}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
            <label htmlFor="selectAll" style={{ cursor: 'pointer', fontWeight: '500' }}>
              Select All ({pendingArtifacts.length} items)
            </label>
          </div>

          {/* Grouped Items */}
          {Object.entries(groupedArtifacts).map(([type, items]) => (
            <div key={type} style={{ marginBottom: '20px' }}>
              <h4 style={{
                margin: '0 0 12px',
                fontSize: '0.875rem',
                color: '#374151',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}>
                <span>{getTypeIcon(type)}</span>
                {getTypeLabel(type)} ({items.length})
              </h4>

              {items.map((artifact) => (
                <div
                  key={artifact.id}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    padding: '12px',
                    background: selectedIds.has(artifact.id) ? '#eff6ff' : 'white',
                    border: `1px solid ${selectedIds.has(artifact.id) ? '#3b82f6' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    marginBottom: '8px',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onClick={() => handleToggle(artifact.id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(artifact.id)}
                    onChange={() => handleToggle(artifact.id)}
                    onClick={e => e.stopPropagation()}
                    style={{ width: '18px', height: '18px', cursor: 'pointer', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontWeight: '500',
                      color: '#111827',
                      fontSize: '0.875rem',
                      marginBottom: '4px',
                    }}>
                      {artifact.title}
                    </div>
                    <div style={{
                      fontSize: '0.8rem',
                      color: '#6b7280',
                      lineHeight: '1.5',
                    }}>
                      {artifact.content?.substring(0, 150)}
                      {artifact.content?.length > 150 ? '...' : ''}
                    </div>
                    {artifact.confidence && (
                      <div style={{
                        marginTop: '8px',
                        fontSize: '0.7rem',
                        color: artifact.confidence > 0.8 ? '#2D7A52' : '#6b7280',
                      }}>
                        Confidence: {Math.round(artifact.confidence * 100)}%
                      </div>
                    )}
                  </div>
                  {artifact.priority && (
                    <span style={{
                      fontSize: '0.7rem',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      height: 'fit-content',
                      background: artifact.priority === 'high' ? '#fee2e2' :
                                  artifact.priority === 'medium' ? '#fef3c7' : '#f3f4f6',
                      color: artifact.priority === 'high' ? '#991b1b' :
                             artifact.priority === 'medium' ? '#92400e' : '#374151',
                    }}>
                      {artifact.priority}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="review-modal-footer">
          <button className="cancel-btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="submit-btn"
            onClick={handleSubmit}
            disabled={selectedIds.size === 0}
            style={{
              opacity: selectedIds.size === 0 ? 0.5 : 1,
              cursor: selectedIds.size === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            Approve & Execute ({selectedIds.size})
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReviewApproveModal;
