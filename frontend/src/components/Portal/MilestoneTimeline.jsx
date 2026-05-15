/**
 * MilestoneTimeline Component
 *
 * Horizontal timeline visualization for the loan milestone journey.
 * Displays milestones with status indicators, dates, and expandable task details.
 */

import React, { useState } from 'react';
import { useTimelineData, useMilestoneMutations } from '../../hooks/usePortalData';
import './MilestoneTimeline.css';

const STATUS_CONFIG = {
  PENDING: {
    color: '#9CA3AF',
    bgColor: '#F3F4F6',
    icon: '○',
    label: 'Pending',
  },
  IN_PROGRESS: {
    color: '#3B82F6',
    bgColor: '#DBEAFE',
    icon: '◐',
    label: 'In Progress',
  },
  COMPLETED: {
    color: '#2D7A52',
    bgColor: '#D1FAE5',
    icon: '●',
    label: 'Completed',
  },
  SKIPPED: {
    color: '#6B7280',
    bgColor: '#E5E7EB',
    icon: '○',
    label: 'Skipped',
  },
};

const TASK_STATUS_CONFIG = {
  PENDING: { color: '#9CA3AF', icon: '○' },
  IN_PROGRESS: { color: '#3B82F6', icon: '◐' },
  COMPLETED: { color: '#2D7A52', icon: '✓' },
  BLOCKED: { color: '#EF4444', icon: '!' },
};

export default function MilestoneTimeline({
  loanId,
  borrowerView = false,
  onMilestoneClick,
  onTaskClick,
  compact = false,
}) {
  const { data, loading, error, refetch } = useTimelineData(loanId, 'horizontal', borrowerView);
  const { updateMilestone, updateTask, loading: mutationLoading } = useMilestoneMutations();
  const [expandedMilestone, setExpandedMilestone] = useState(null);

  if (loading) {
    return <TimelineSkeleton compact={compact} />;
  }

  if (error) {
    return (
      <div className="timeline-error">
        <span className="error-icon">⚠️</span>
        <p>Failed to load milestone timeline</p>
        <button onClick={refetch} className="retry-btn">
          Try Again
        </button>
      </div>
    );
  }

  if (!data || !data.milestones || data.milestones.length === 0) {
    return (
      <div className="timeline-empty">
        <span className="empty-icon">📋</span>
        <p>No milestones have been created yet</p>
      </div>
    );
  }

  const { milestones, progress } = data;

  const handleMilestoneToggle = (milestoneId) => {
    setExpandedMilestone(expandedMilestone === milestoneId ? null : milestoneId);
  };

  const handleTaskComplete = async (taskId) => {
    try {
      await updateTask(taskId, 'COMPLETED');
      refetch();
    } catch (err) {
      console.error('Failed to complete task:', err);
    }
  };

  return (
    <div className={`milestone-timeline ${compact ? 'compact' : ''}`}>
      {/* Progress Header */}
      <div className="timeline-header">
        <div className="progress-summary">
          <span className="progress-text">
            {progress.completed} of {progress.total} milestones complete
          </span>
          <span className="progress-percent">{progress.progress_percent}%</span>
        </div>
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${progress.progress_percent}%` }}
          />
        </div>
      </div>

      {/* Timeline Container */}
      <div className="timeline-container">
        <div className="timeline-track" />

        {/* Milestone Nodes */}
        <div className="milestones-row">
          {milestones.map((milestone, index) => {
            const statusConfig = STATUS_CONFIG[milestone.status] || STATUS_CONFIG.PENDING;
            const isExpanded = expandedMilestone === milestone.id;
            const isClickable = onMilestoneClick || milestone.tasks?.length > 0;

            return (
              <div
                key={milestone.id}
                className={`milestone-node ${milestone.status.toLowerCase()} ${isExpanded ? 'expanded' : ''}`}
                style={{ '--milestone-color': statusConfig.color }}
              >
                {/* Connector Line */}
                {index < milestones.length - 1 && (
                  <div
                    className={`connector-line ${milestone.status === 'COMPLETED' ? 'completed' : ''}`}
                  />
                )}

                {/* Milestone Circle */}
                <button
                  className="milestone-circle"
                  onClick={() => {
                    if (onMilestoneClick) {
                      onMilestoneClick(milestone);
                    }
                    if (milestone.tasks?.length > 0) {
                      handleMilestoneToggle(milestone.id);
                    }
                  }}
                  disabled={!isClickable}
                  style={{
                    backgroundColor: statusConfig.bgColor,
                    borderColor: statusConfig.color,
                  }}
                >
                  <span
                    className="milestone-icon"
                    style={{ color: statusConfig.color }}
                  >
                    {milestone.icon || statusConfig.icon}
                  </span>
                </button>

                {/* Milestone Label */}
                <div className="milestone-label">
                  <span className="milestone-name">{milestone.name}</span>
                  {milestone.target_date && (
                    <span className="milestone-date">
                      {formatDate(milestone.target_date)}
                    </span>
                  )}
                  <span
                    className="milestone-status"
                    style={{ color: statusConfig.color }}
                  >
                    {statusConfig.label}
                  </span>
                </div>

                {/* Expanded Task List */}
                {isExpanded && milestone.tasks && milestone.tasks.length > 0 && (
                  <div className="milestone-tasks">
                    <div className="tasks-header">
                      <span>Tasks</span>
                      <span className="tasks-count">
                        {milestone.tasks.filter((t) => t.status === 'COMPLETED').length}/
                        {milestone.tasks.length}
                      </span>
                    </div>
                    <ul className="tasks-list">
                      {milestone.tasks.map((task) => {
                        const taskConfig = TASK_STATUS_CONFIG[task.status] || TASK_STATUS_CONFIG.PENDING;
                        return (
                          <li
                            key={task.id}
                            className={`task-item ${task.status.toLowerCase()}`}
                          >
                            <span
                              className="task-icon"
                              style={{ color: taskConfig.color }}
                            >
                              {taskConfig.icon}
                            </span>
                            <span className="task-name">{task.name}</span>
                            {task.is_borrower_action && task.status !== 'COMPLETED' && (
                              <button
                                className="task-complete-btn"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (onTaskClick) {
                                    onTaskClick(task);
                                  } else {
                                    handleTaskComplete(task.id);
                                  }
                                }}
                                disabled={mutationLoading}
                              >
                                Complete
                              </button>
                            )}
                            {task.is_borrower_action && (
                              <span className="borrower-action-badge">Your Action</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Current Milestone Indicator */}
      {progress.current_milestone && (
        <div className="current-milestone-badge">
          <span className="badge-icon">📍</span>
          <span>Current: {progress.current_milestone.name}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Loading skeleton for timeline
 */
function TimelineSkeleton({ compact }) {
  return (
    <div className={`milestone-timeline skeleton ${compact ? 'compact' : ''}`}>
      <div className="timeline-header">
        <div className="skeleton-text" style={{ width: '200px', height: '20px' }} />
        <div className="skeleton-bar" style={{ width: '100%', height: '8px' }} />
      </div>
      <div className="timeline-container">
        <div className="milestones-row">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="milestone-node skeleton">
              <div className="skeleton-circle" />
              <div className="milestone-label">
                <div className="skeleton-text" style={{ width: '80px' }} />
                <div className="skeleton-text" style={{ width: '60px' }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Format date for display
 */
function formatDate(dateString) {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Vertical Timeline Variant
 */
export function MilestoneTimelineVertical({
  loanId,
  borrowerView = false,
  onMilestoneClick,
  onTaskClick,
}) {
  const { data, loading, error, refetch } = useTimelineData(loanId, 'vertical', borrowerView);
  const { updateTask, loading: mutationLoading } = useMilestoneMutations();

  if (loading) {
    return <VerticalTimelineSkeleton />;
  }

  if (error) {
    return (
      <div className="timeline-error">
        <span className="error-icon">⚠️</span>
        <p>Failed to load milestone timeline</p>
        <button onClick={refetch} className="retry-btn">
          Try Again
        </button>
      </div>
    );
  }

  if (!data || !data.milestones || data.milestones.length === 0) {
    return (
      <div className="timeline-empty">
        <span className="empty-icon">📋</span>
        <p>No milestones have been created yet</p>
      </div>
    );
  }

  const { milestones, progress } = data;

  const handleTaskComplete = async (taskId) => {
    try {
      await updateTask(taskId, 'COMPLETED');
      refetch();
    } catch (err) {
      console.error('Failed to complete task:', err);
    }
  };

  return (
    <div className="milestone-timeline-vertical">
      {/* Progress Header */}
      <div className="timeline-header">
        <h3>Loan Journey</h3>
        <div className="progress-summary">
          <span className="progress-text">
            {progress.completed}/{progress.total} complete
          </span>
          <div className="progress-bar-small">
            <div
              className="progress-fill"
              style={{ width: `${progress.progress_percent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Vertical Timeline */}
      <div className="vertical-timeline">
        {milestones.map((milestone, index) => {
          const statusConfig = STATUS_CONFIG[milestone.status] || STATUS_CONFIG.PENDING;
          const isLast = index === milestones.length - 1;

          return (
            <div
              key={milestone.id}
              className={`vertical-milestone ${milestone.status.toLowerCase()}`}
            >
              {/* Timeline Line */}
              {!isLast && (
                <div
                  className={`vertical-line ${milestone.status === 'COMPLETED' ? 'completed' : ''}`}
                />
              )}

              {/* Milestone Node */}
              <div className="vertical-node">
                <div
                  className="node-circle"
                  style={{
                    backgroundColor: statusConfig.bgColor,
                    borderColor: statusConfig.color,
                  }}
                >
                  <span style={{ color: statusConfig.color }}>
                    {milestone.icon || statusConfig.icon}
                  </span>
                </div>

                <div className="node-content">
                  <div className="node-header">
                    <h4
                      className="node-title"
                      onClick={() => onMilestoneClick && onMilestoneClick(milestone)}
                    >
                      {milestone.name}
                    </h4>
                    <span
                      className="node-status"
                      style={{ color: statusConfig.color }}
                    >
                      {statusConfig.label}
                    </span>
                  </div>

                  {milestone.description && (
                    <p className="node-description">{milestone.description}</p>
                  )}

                  {milestone.target_date && (
                    <span className="node-date">
                      {milestone.status === 'COMPLETED'
                        ? `Completed ${formatDate(milestone.completed_at)}`
                        : `Target: ${formatDate(milestone.target_date)}`}
                    </span>
                  )}

                  {/* Tasks */}
                  {milestone.tasks && milestone.tasks.length > 0 && (
                    <div className="node-tasks">
                      {milestone.tasks.map((task) => {
                        const taskConfig = TASK_STATUS_CONFIG[task.status] || TASK_STATUS_CONFIG.PENDING;
                        return (
                          <div
                            key={task.id}
                            className={`node-task ${task.status.toLowerCase()}`}
                          >
                            <span
                              className="task-icon"
                              style={{ color: taskConfig.color }}
                            >
                              {taskConfig.icon}
                            </span>
                            <span className="task-name">{task.name}</span>
                            {task.is_borrower_action && task.status !== 'COMPLETED' && (
                              <button
                                className="task-action-btn"
                                onClick={() => {
                                  if (onTaskClick) {
                                    onTaskClick(task);
                                  } else {
                                    handleTaskComplete(task.id);
                                  }
                                }}
                                disabled={mutationLoading}
                              >
                                Complete
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VerticalTimelineSkeleton() {
  return (
    <div className="milestone-timeline-vertical skeleton">
      <div className="timeline-header">
        <div className="skeleton-text" style={{ width: '150px', height: '24px' }} />
      </div>
      <div className="vertical-timeline">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="vertical-milestone skeleton">
            <div className="vertical-node">
              <div className="skeleton-circle" />
              <div className="node-content">
                <div className="skeleton-text" style={{ width: '120px' }} />
                <div className="skeleton-text" style={{ width: '200px' }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
