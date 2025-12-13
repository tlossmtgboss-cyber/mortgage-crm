import React from 'react';
import './TasksSkeleton.css';

/**
 * Skeleton loader for the Tasks page that matches the exact layout structure.
 * This prevents layout shifts when loading completes.
 */
const TasksSkeleton = () => {
  return (
    <div className="tasks-page tasks-skeleton">
      {/* Page Header */}
      <div className="page-header">
        <div className="skeleton-text skeleton-title"></div>
        <div className="skeleton-text skeleton-subtitle"></div>
      </div>

      {/* Tab Navigation */}
      <div className="task-tabs">
        <div className="skeleton-tab active"></div>
        <div className="skeleton-tab"></div>
        <div className="skeleton-tab"></div>
        <div className="skeleton-tab"></div>
      </div>

      {/* Email Layout Structure */}
      <div className="tab-content">
        <div className="email-layout">
          {/* Task List (Left Side) */}
          <div className="task-inbox">
            <div className="inbox-header">
              <div className="inbox-header-left">
                <div className="skeleton-checkbox"></div>
                <div className="skeleton-text skeleton-header-text"></div>
                <div className="skeleton-badge"></div>
              </div>
            </div>
            <div className="inbox-list">
              {/* Generate 8 skeleton task items */}
              {[...Array(8)].map((_, i) => (
                <div key={i} className={`inbox-item skeleton-item ${i === 0 ? 'selected' : ''}`}>
                  <div className="inbox-item-header">
                    <div className="skeleton-checkbox"></div>
                    <div className="skeleton-icon"></div>
                    <div className="skeleton-text skeleton-task-title"></div>
                  </div>
                  <div className="inbox-item-meta">
                    <div className="skeleton-text skeleton-client-name"></div>
                    <div className="skeleton-dot"></div>
                  </div>
                  <div className="skeleton-text skeleton-preview"></div>
                </div>
              ))}
            </div>
          </div>

          {/* Task Detail (Right Side) */}
          <div className="task-detail-panel skeleton-detail-panel">
            <div className="task-detail-main">
              {/* Header */}
              <div className="task-detail-header skeleton-header">
                <div className="skeleton-text skeleton-detail-title"></div>
                <div className="skeleton-row">
                  <div className="skeleton-label-value"></div>
                  <div className="skeleton-label-value"></div>
                </div>
                <div className="skeleton-row">
                  <div className="skeleton-label-value"></div>
                  <div className="skeleton-label-value"></div>
                </div>
              </div>

              {/* Send Via Section */}
              <div className="skeleton-section">
                <div className="skeleton-text skeleton-section-label"></div>
                <div className="skeleton-button-group">
                  <div className="skeleton-button"></div>
                  <div className="skeleton-button active"></div>
                  <div className="skeleton-button"></div>
                  <div className="skeleton-button"></div>
                </div>
              </div>

              {/* What to Accomplish */}
              <div className="skeleton-card">
                <div className="skeleton-text skeleton-card-title"></div>
                <div className="skeleton-text skeleton-card-content"></div>
                <div className="skeleton-text skeleton-card-content short"></div>
              </div>

              {/* Train AI Section */}
              <div className="skeleton-card highlight">
                <div className="skeleton-text skeleton-card-title"></div>
                <div className="skeleton-textarea"></div>
              </div>

              {/* AI Message Section */}
              <div className="skeleton-card message">
                <div className="skeleton-text skeleton-card-title"></div>
                <div className="skeleton-message-content">
                  <div className="skeleton-text skeleton-line"></div>
                  <div className="skeleton-text skeleton-line"></div>
                  <div className="skeleton-text skeleton-line short"></div>
                  <div className="skeleton-text skeleton-line"></div>
                  <div className="skeleton-text skeleton-line medium"></div>
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="task-detail-actions skeleton-actions">
              <div className="skeleton-action-button primary"></div>
              <div className="skeleton-action-button"></div>
              <div className="skeleton-action-button"></div>
              <div className="skeleton-action-button"></div>
              <div className="skeleton-action-button success"></div>
              <div className="skeleton-action-button danger"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TasksSkeleton;
