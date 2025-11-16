import React from 'react';
import './ArchivedResponsibilitiesModal.css';

/**
 * ArchivedResponsibilitiesModal - View and restore archived responsibilities
 *
 * Features:
 * - Display all archived responsibilities in a grayed-out style
 * - Restore functionality with confirmation
 * - Empty state when no archived items
 * - Shows same info as regular cards but read-only
 */

function ArchivedResponsibilitiesModal({ archivedResponsibilities, onRestore, onClose, isRestoring }) {
  const formatDate = (dateString) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getPriorityClass = (priority) => {
    const classes = {
      'critical': 'priority-critical',
      'high': 'priority-high',
      'medium': 'priority-medium',
      'low': 'priority-low'
    };
    return classes[priority] || 'priority-medium';
  };

  const getOwnershipDisplay = (ownership) => {
    const displays = {
      'primary': { text: 'Primary', icon: '⭐' },
      'secondary': { text: 'Secondary', icon: '➕' },
      'shared': { text: 'Shared', icon: '🤝' }
    };
    return displays[ownership] || displays['primary'];
  };

  const handleRestore = (responsibility) => {
    if (window.confirm(`Restore "${responsibility.title}" to active responsibilities?`)) {
      onRestore(responsibility.id);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content archived-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Archived Responsibilities ({archivedResponsibilities.length})</h3>
          <button onClick={onClose} className="btn-close">×</button>
        </div>

        <div className="modal-body">
          {archivedResponsibilities.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🗄️</div>
              <h4>No Archived Responsibilities</h4>
              <p>When you archive a responsibility, it will appear here.</p>
            </div>
          ) : (
            <div className="archived-list">
              {archivedResponsibilities.map(resp => {
                const ownershipInfo = getOwnershipDisplay(resp.ownership);

                return (
                  <div key={resp.id} className="archived-card">
                    <div className="archived-card-header">
                      <h4 className="card-title">
                        <span className="title-icon">📋</span>
                        {resp.title}
                      </h4>
                      <button
                        onClick={() => handleRestore(resp)}
                        className="btn-restore"
                        disabled={isRestoring}
                        title="Restore to active responsibilities"
                      >
                        {isRestoring ? '↻' : '↶'} Restore
                      </button>
                    </div>

                    <div className="archived-card-body">
                      {/* Info Grid */}
                      <div className="info-grid">
                        <div className="info-item">
                          <span className="label">Ownership:</span>
                          <span className="value">
                            <span className="ownership-icon">{ownershipInfo.icon}</span>
                            {ownershipInfo.text}
                          </span>
                        </div>

                        <div className="info-item">
                          <span className="label">Time:</span>
                          <span className="value">{resp.time_allocation || 0}%</span>
                        </div>

                        <div className="info-item">
                          <span className="label">Priority:</span>
                          <span className={`priority-badge ${getPriorityClass(resp.priority)}`}>
                            {resp.priority}
                          </span>
                        </div>

                        <div className="info-item">
                          <span className="label">Effective:</span>
                          <span className="value date-range">
                            {formatDate(resp.effective_date)}
                            {' - '}
                            {resp.end_date ? formatDate(resp.end_date) : 'Present'}
                          </span>
                        </div>
                      </div>

                      {/* Skills */}
                      {resp.required_skills && resp.required_skills.length > 0 && (
                        <div className="skills-section">
                          <span className="label">Required Skills:</span>
                          <div className="skills-tags">
                            {resp.required_skills.map(skill => (
                              <span key={skill.id} className="skill-tag">
                                {skill.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Description */}
                      {resp.description && (
                        <div className="description-section">
                          <span className="label">Description:</span>
                          <p className="description">{resp.description}</p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button onClick={onClose} className="btn-close-modal">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default ArchivedResponsibilitiesModal;
