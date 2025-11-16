import React from 'react';
import './PermissionDiffModal.css';

function PermissionDiffModal({ diff, templateName, onClose }) {
  const formatPermissionKey = (key) => {
    const parts = key.split('.');
    if (parts.length === 2) {
      const category = parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
      const action = parts[1]
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
      return `${category}: ${action}`;
    }
    return key;
  };

  const formatTemplateName = (template) => {
    if (!template) return 'Unknown';
    return template.charAt(0).toUpperCase() + template.slice(1);
  };

  const hasChanges = diff.added.length > 0 || diff.removed.length > 0;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="permission-diff-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Template Applied: {formatTemplateName(templateName)}</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {!hasChanges && (
            <div className="no-changes-message">
              <div className="info-icon">ℹ️</div>
              <p>No permission changes were made. The user already has all permissions from this template.</p>
            </div>
          )}

          {hasChanges && (
            <>
              <div className="diff-summary">
                <div className="summary-item summary-added">
                  <span className="summary-count">{diff.added.length}</span>
                  <span className="summary-label">Added</span>
                </div>
                <div className="summary-item summary-removed">
                  <span className="summary-count">{diff.removed.length}</span>
                  <span className="summary-label">Removed</span>
                </div>
                <div className="summary-item summary-unchanged">
                  <span className="summary-count">{diff.unchanged.length}</span>
                  <span className="summary-label">Unchanged</span>
                </div>
              </div>

              <div className="diff-sections">
                {diff.added.length > 0 && (
                  <div className="diff-section added-section">
                    <h3 className="section-title">
                      <span className="icon">✅</span>
                      Permissions Added ({diff.added.length})
                    </h3>
                    <div className="permission-list">
                      {diff.added.map((key) => (
                        <div key={key} className="permission-item added-item">
                          <span className="permission-key">{formatPermissionKey(key)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {diff.removed.length > 0 && (
                  <div className="diff-section removed-section">
                    <h3 className="section-title">
                      <span className="icon">❌</span>
                      Permissions Removed ({diff.removed.length})
                    </h3>
                    <div className="permission-list">
                      {diff.removed.map((key) => (
                        <div key={key} className="permission-item removed-item">
                          <span className="permission-key">{formatPermissionKey(key)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {diff.unchanged.length > 0 && (
                  <div className="diff-section unchanged-section">
                    <h3 className="section-title">
                      <span className="icon">➖</span>
                      Unchanged Permissions ({diff.unchanged.length})
                    </h3>
                    <div className="permission-list collapsed">
                      {diff.unchanged.slice(0, 5).map((key) => (
                        <div key={key} className="permission-item unchanged-item">
                          <span className="permission-key">{formatPermissionKey(key)}</span>
                        </div>
                      ))}
                      {diff.unchanged.length > 5 && (
                        <div className="more-indicator">
                          ... and {diff.unchanged.length - 5} more unchanged
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <p className="footer-note">
            The template has been applied successfully. You can further customize individual permissions below.
          </p>
          <button className="close-footer-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default PermissionDiffModal;
