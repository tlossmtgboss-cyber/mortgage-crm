/**
 * Active Loan Portal
 *
 * Portal view for borrowers with active loans in progress.
 * Receives data from PortalContainer parent component.
 *
 * Features:
 * - Loan status and terms display
 * - Document needs list and uploads
 * - Task management
 * - Timeline/milestones
 * - Appointment scheduling
 * - Payment calculators
 * - Messages with loan team
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../../lib/api';
import ScheduleAppointmentModal from '../../components/ScheduleAppointmentModal';
import PaymentCalculator from '../../components/PaymentCalculator';
import ApplicantTasks from '../../components/Portal/ApplicantTasks';
import PortalDocumentRequirements from '../../components/Portal/PortalDocumentRequirements';
import TotalCostAnalysis from '../../components/Portal/TotalCostAnalysis';
import PortalVideoMessages from '../../components/Portal/PortalVideoMessages';
import VideoLightbox from '../../components/Portal/VideoLightbox';
import '../PURLPortal.css';
import { toast } from '../../utils/toast';

// Tab components - Arrow/chevron style with notification dots or count badges
const TabButton = ({ label, isActive, onClick, hasNotification, badgeCount, isFirst, isLast }) => (
  <button
    className={`purl-tab-btn ${isActive ? 'active' : ''} ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}`}
    onClick={onClick}
  >
    <span className="tab-label">{label}</span>
    {/* Show red number badge for count > 0, otherwise just a dot for boolean notification */}
    {badgeCount > 0 ? (
      <span className="tab-notification-badge">{badgeCount}</span>
    ) : (
      hasNotification && <span className="tab-notification-dot" />
    )}
  </button>
);

// Progress bar component
const ProgressBar = ({ percentage, label }) => (
  <div className="purl-progress-container">
    <div className="progress-header">
      <span>{label}</span>
      <span>{percentage}%</span>
    </div>
    <div className="progress-bar">
      <div className="progress-fill" style={{ width: `${percentage}%` }} />
    </div>
  </div>
);

// Status badge component
const StatusBadge = ({ status }) => {
  const statusConfig = {
    lead: { label: 'Getting Started', color: 'blue' },
    application: { label: 'Application', color: 'yellow' },
    active_loan: { label: 'In Progress', color: 'green' },
    preapproval: { label: 'Pre-Approval', color: 'blue' },
    under_contract: { label: 'Under Contract', color: 'yellow' },
    processing: { label: 'Processing', color: 'orange' },
    clear_to_close: { label: 'Clear to Close', color: 'emerald' },
    funded: { label: 'Funded', color: 'emerald' },
    closed: { label: 'Closed', color: 'gray' }
  };

  const config = statusConfig[status] || { label: status, color: 'gray' };

  return (
    <span className={`status-badge status-${config.color}`}>
      {config.label}
    </span>
  );
};

// Header Milestone Progress - Horizontal step indicator for loan stages
const HeaderMilestoneProgress = ({ subStage, workspaceStatus, leadStage }) => {
  // Use the actual CRM lead stage if available, otherwise fall back to workspace status
  const crmStage = leadStage?.toLowerCase() || '';
  const status = subStage || workspaceStatus || '';
  const statusLower = status?.toLowerCase() || '';

  // Check if we're in the lead stage (pre-approval journey) based on CRM lead stage
  // CRM Lead stages: new, contacted, qualified, nurturing, pre_qualified, pre_approved, under_contract, won, lost
  const isLeadStage = crmStage && !['under_contract', 'won', 'lost'].includes(crmStage);

  // Define lead journey milestones
  // App Completed → Docs Requested → Docs Approved → Pre Approved
  const leadStages = [
    { id: 'app_completed', label: 'Application Completed', shortLabel: 'App Completed' },
    { id: 'docs_requested', label: 'Docs Requested', shortLabel: 'Docs Requested' },
    { id: 'docs_approved', label: 'Docs Approved', shortLabel: 'Docs Approved' },
    { id: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre Approved' },
  ];

  // Define full loan journey stages (after contract received)
  const loanStages = [
    { id: 'processing', label: 'Processing', shortLabel: 'Processing' },
    { id: 'underwriting', label: 'Underwriting', shortLabel: 'Underwriting' },
    { id: 'approval', label: 'Approval', shortLabel: 'Approved' },
    { id: 'clear_to_close', label: 'Clear to Close', shortLabel: 'Clear to Close' },
    { id: 'closing', label: 'Closing', shortLabel: 'Closing' },
  ];

  // Use appropriate stages based on current phase
  const stages = isLeadStage ? leadStages : loanStages;

  // Determine current stage index based on CRM lead stage
  const getCurrentStageIndex = () => {
    if (isLeadStage) {
      // Map CRM lead stages to milestone progress (4 stages total):
      // App Completed (index 1) - new, contacted = application just submitted
      // Docs Requested (index 2) - qualified, nurturing = docs requested
      // Docs Approved (index 3) - pre_qualified = docs reviewed/approved
      // Pre Approved (index 4) - pre_approved = pre-approval issued
      const crmStageToIndex = {
        'new': 1,           // App completed, starting docs
        'contacted': 1,     // App completed, starting docs
        'qualified': 2,     // Docs have been requested
        'nurturing': 2,     // Docs have been requested
        'pre_qualified': 3, // Docs approved, pre-approval in progress
        'pre_approved': 4,  // Pre-approved (all complete)
      };
      return crmStageToIndex[crmStage] ?? 1; // Default: app completed
    } else {
      // Full loan process mapping (after contract received)
      const loanStatusToIndex = {
        'processing': 1,
        'underwriting': 2,
        'conditional_approval': 3,
        'approved': 3,
        'approval': 3,
        'clear_to_close': 4,
        'ctc': 4,
        'closing': 5,
        'docs_out': 5,
        'docs_back': 5,
        'funded': 5,
        'closed': 5,
      };
      return loanStatusToIndex[statusLower] ?? 0;
    }
  };

  const currentIndex = getCurrentStageIndex();

  return (
    <div className="header-milestone-progress">
      <div className="milestone-steps">
        {stages.map((stage, index) => {
          const isComplete = index < currentIndex;
          const isCurrent = index === currentIndex;
          const isPending = index > currentIndex;

          return (
            <div
              key={stage.id}
              className={`milestone-step ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} ${isPending ? 'pending' : ''}`}
            >
              <div className="step-indicator">
                {isComplete ? (
                  <span className="step-check">✓</span>
                ) : (
                  <span className="step-number">{index + 1}</span>
                )}
              </div>
              <span className="step-label">{stage.shortLabel}</span>
              {index < stages.length - 1 && (
                <div className={`step-connector ${isComplete ? 'complete' : ''}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Document card component
const DocumentStatusBadge = ({ status }) => {
  const statusConfig = {
    pending: { label: 'Pending Review', className: 'status-pending' },
    approved: { label: 'Approved', className: 'status-approved' },
    rejected: { label: 'Needs Revision', className: 'status-rejected' },
    uploaded: { label: 'Uploaded', className: 'status-uploaded' },
    scanning: { label: 'Scanning', className: 'status-pending' },
    processing: { label: 'Processing', className: 'status-pending' },
    deleted: { label: 'Removed', className: 'status-rejected' },
    expired: { label: 'Expired', className: 'status-rejected' },
    error: { label: 'Error', className: 'status-rejected' },
    outstanding: { label: 'Outstanding', className: 'status-outstanding' },
  };

  // Normalize status to lowercase for lookup
  const statusLower = (status || 'pending').toLowerCase();
  const config = statusConfig[statusLower] || statusConfig.pending;

  return (
    <span className={`doc-status-badge ${config.className}`}>
      {config.label}
    </span>
  );
};

const DocumentsTable = ({ documents, onDownload }) => {
  if (documents.length === 0) {
    return (
      <div className="empty-state-card">
        <div className="empty-icon">📁</div>
        <h3>No documents yet</h3>
        <p>Documents you upload will appear here</p>
      </div>
    );
  }

  return (
    <div className="documents-table-wrapper">
      <table className="documents-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Type</th>
            <th>Status</th>
            <th>Uploaded</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map(doc => (
            <tr key={doc.id}>
              <td className="doc-name-cell">
                <span className="doc-icon">📄</span>
                <span className="doc-filename">{doc.filename}</span>
              </td>
              <td className="doc-type-cell">
                {doc.document_type || '—'}
              </td>
              <td className="doc-status-cell">
                <DocumentStatusBadge status={doc.status} />
              </td>
              <td className="doc-date-cell">
                {new Date(doc.uploaded_at).toLocaleDateString()}
              </td>
              <td className="doc-actions-cell">
                <button
                  className="action-btn download"
                  onClick={() => onDownload(doc.id)}
                  title="Download"
                >
                  ↓
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// Task status badge component
const TaskStatusBadge = ({ status, isOverdue }) => {
  const statusConfig = {
    open: { label: 'To Do', className: 'status-todo' },
    TODO: { label: 'To Do', className: 'status-todo' },
    IN_PROGRESS: { label: 'In Progress', className: 'status-progress' },
    completed: { label: 'Completed', className: 'status-completed' },
    DONE: { label: 'Completed', className: 'status-completed' },
  };

  const config = statusConfig[status] || statusConfig.open;

  if (isOverdue && status !== 'completed' && status !== 'DONE') {
    return <span className="task-status-badge status-overdue">Overdue</span>;
  }

  return <span className={`task-status-badge ${config.className}`}>{config.label}</span>;
};

// Priority badge component
const PriorityBadge = ({ priority }) => {
  const priorityConfig = {
    high: { label: 'High', className: 'priority-high' },
    medium: { label: 'Medium', className: 'priority-medium' },
    low: { label: 'Low', className: 'priority-low' },
  };

  const config = priorityConfig[priority] || priorityConfig.medium;

  return <span className={`priority-badge ${config.className}`}>{config.label}</span>;
};

// Tasks table component
const TasksTable = ({ tasks, onComplete, title, showCompleted = false }) => {
  if (tasks.length === 0) {
    return (
      <div className="empty-state-card">
        <div className="empty-icon">{showCompleted ? '🎉' : '✓'}</div>
        <h3>{showCompleted ? 'No completed tasks yet' : 'All caught up!'}</h3>
        <p>{showCompleted ? 'Completed tasks will appear here' : 'You have no pending tasks'}</p>
      </div>
    );
  }

  return (
    <div className="tasks-table-wrapper">
      <table className="tasks-table">
        <thead>
          <tr>
            <th style={{ width: '40px' }}></th>
            <th>Task</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Due Date</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(task => {
            const isOverdue = task.due_at && new Date(task.due_at) < new Date();
            const isCompleted = task.status === 'completed' || task.status === 'DONE';

            return (
              <tr key={task.id} className={isCompleted ? 'completed-row' : ''}>
                <td className="checkbox-cell">
                  <input
                    type="checkbox"
                    className="task-checkbox"
                    checked={isCompleted}
                    onChange={() => onComplete(task.id, !isCompleted)}
                    disabled={isCompleted}
                  />
                </td>
                <td className="task-name-cell">
                  <span className={`task-title ${isCompleted ? 'completed' : ''}`}>
                    {task.title}
                  </span>
                  {task.description && (
                    <span className="task-description">{task.description}</span>
                  )}
                </td>
                <td className="task-status-cell">
                  <TaskStatusBadge status={task.status} isOverdue={isOverdue} />
                </td>
                <td className="task-priority-cell">
                  <PriorityBadge priority={task.priority} />
                </td>
                <td className="task-date-cell">
                  {task.due_at ? (
                    <span className={isOverdue && !isCompleted ? 'overdue-date' : ''}>
                      {new Date(task.due_at).toLocaleDateString()}
                    </span>
                  ) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// Legacy Task card component (for overview)
const TaskCard = ({ task, onComplete }) => {
  const isOverdue = task.due_at && new Date(task.due_at) < new Date();
  const isCompleted = task.status === 'completed' || task.status === 'DONE';

  return (
    <div className={`task-card ${isCompleted ? 'completed' : ''} ${isOverdue ? 'overdue' : ''}`}>
      <div className="task-checkbox">
        <input
          type="checkbox"
          checked={isCompleted}
          onChange={() => onComplete(task.id, !isCompleted)}
          disabled={isCompleted}
        />
      </div>
      <div className="task-content">
        <div className="task-title">{task.title}</div>
        {task.description && <div className="task-desc">{task.description}</div>}
        <div className="task-meta">
          {task.due_at && (
            <span className={`due-date ${isOverdue ? 'overdue' : ''}`}>
              Due: {new Date(task.due_at).toLocaleDateString()}
            </span>
          )}
          {task.priority && <PriorityBadge priority={task.priority} />}
        </div>
      </div>
    </div>
  );
};

// Milestone component
const MilestoneTracker = ({ milestones }) => {
  if (!milestones || milestones.length === 0) {
    return <div className="no-milestones">No milestones yet</div>;
  }

  const completedCount = milestones.filter(m => m.status === 'completed').length;

  return (
    <div className="milestone-tracker">
      <div className="milestone-summary">
        <span className="milestone-count">{completedCount} of {milestones.length} complete</span>
      </div>
      <div className="milestone-timeline">
        {milestones.map((milestone, index) => (
          <div key={milestone.id || index} className={`milestone-item status-${milestone.status}`}>
            <div className="milestone-dot">
              {milestone.status === 'completed' ? '✓' :
               milestone.status === 'in_progress' ? '●' : '○'}
            </div>
            <div className="milestone-info">
              <div className="milestone-name">{milestone.name}</div>
              {milestone.completed_at && (
                <div className="milestone-date">
                  Completed: {new Date(milestone.completed_at).toLocaleDateString()}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Timeline event component
const TimelineEvent = ({ event }) => {
  const typeIcons = {
    document: '📄',
    task: '✓',
    milestone: '🏆',
    message: '💬',
    status: '📊',
    application: '📝'
  };

  return (
    <div className="timeline-event">
      <div className="event-icon">{typeIcons[event.event_type] || '●'}</div>
      <div className="event-content">
        <div className="event-title">{event.title}</div>
        {event.description && <div className="event-desc">{event.description}</div>}
        <div className="event-time">
          {new Date(event.created_at).toLocaleString()}
        </div>
      </div>
    </div>
  );
};

// Message component
const MessageItem = ({ message, isMine }) => (
  <div className={`message-item ${isMine ? 'outbound' : 'inbound'}`}>
    <div className="message-header">
      <span className="sender">{message.sender_name}</span>
      <span className="time">{new Date(message.created_at).toLocaleString()}</span>
    </div>
    {message.subject && <div className="message-subject">{message.subject}</div>}
    <div className="message-body">{message.body}</div>
  </div>
);

// Helper function to format address
const formatAddress = (address) => {
  if (!address) return 'Address pending';
  if (typeof address === 'string') return address;
  const parts = [address.street, address.city, address.state, address.zip_code].filter(Boolean);
  return parts.join(', ') || 'Address pending';
};

// Helper function to format currency
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

// Helper function to format date
const formatDate = (dateStr) => {
  if (!dateStr) return 'TBD';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

// Helper function to calculate days until close
const daysUntilClose = (closeDate) => {
  if (!closeDate) return null;
  const today = new Date();
  const close = new Date(closeDate);
  const diffTime = close - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
};

// Helper function to get user initials
const getInitials = (name) => {
  if (!name) return '?';
  const parts = name.trim().split(' ');
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return parts[0][0].toUpperCase();
};

// Helper function to format current date
const formatCurrentDate = () => {
  const now = new Date();
  return now.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
};

// Days Until Closing Counter Component
const DaysCounterCard = ({ closeDate, estimatedCloseDate }) => {
  const targetDate = closeDate || estimatedCloseDate;
  const daysLeft = daysUntilClose(targetDate);

  // Convert days to two-digit display
  const displayDays = daysLeft !== null && daysLeft >= 0 ? daysLeft : 0;
  const digit1 = Math.floor(displayDays / 10);
  const digit2 = displayDays % 10;

  return (
    <div className="days-counter-card">
      <div className="days-counter-header">Days Until Closing</div>
      <div className="days-counter-display">
        <div className="days-digit animated">{digit1}</div>
        <div className="days-digit animated">{digit2}</div>
      </div>
      <div className="days-counter-label">
        {daysLeft === null ? 'Closing date TBD' :
         daysLeft === 0 ? 'Closing Today!' :
         daysLeft < 0 ? 'Past closing date' :
         daysLeft === 1 ? 'Day remaining' : 'Days remaining'}
      </div>
      {targetDate && (
        <div className="days-counter-subtext">
          {closeDate ? 'Scheduled' : 'Estimated'}: {formatDate(targetDate)}
        </div>
      )}
    </div>
  );
};

// Loan Status Card with House Illustration
const LoanStatusCard = ({ loan, workspace, subStage }) => {
  // Calculate progress percentage based on stage
  const getProgressPercentage = () => {
    const stageProgress = {
      'lead': 10,
      'application': 20,
      'preapproval': 30,
      'pre_qualified': 40,
      'pre_approved': 50,
      'processing': 60,
      'underwriting': 70,
      'approved': 80,
      'clear_to_close': 90,
      'closing': 95,
      'funded': 100,
    };
    const status = subStage?.toLowerCase() || workspace?.status?.toLowerCase() || 'application';
    return stageProgress[status] || 20;
  };

  const progressPct = getProgressPercentage();
  const statusLabel = subStage || workspace?.status || 'In Progress';

  return (
    <div className="loan-status-card">
      <div className="loan-status-header">
        <h2>Loan Status</h2>
      </div>
      <div className="loan-status-content">
        <div className="house-illustration">
          🏠
        </div>
        <div className="loan-status-details">
          <div className="status-progress-bar">
            <div className="status-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="status-text">
            Your loan is currently in <strong>{statusLabel}</strong> ({progressPct}% complete)
          </div>
        </div>
      </div>
    </div>
  );
};

// Recent Activity Sidebar Component
const RecentActivitySidebar = ({ timeline, onViewAll }) => {
  const typeIcons = {
    document: '📄',
    task: '✓',
    milestone: '🏆',
    message: '💬',
    status: '📊',
    application: '📝'
  };

  const getIconClass = (type) => {
    const typeMap = {
      document: 'document',
      task: 'task',
      milestone: 'milestone',
      message: 'message',
      status: 'status',
      application: 'document'
    };
    return typeMap[type] || 'status';
  };

  // Get relative time string
  const getRelativeTime = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  // Check if activity is new (within last 24 hours)
  const isNew = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    return (now - date) < 86400000; // 24 hours in ms
  };

  return (
    <div className="recent-activity-card">
      <div className="activity-card-header">
        <h3>Recent Activity</h3>
        {timeline.length > 5 && (
          <button className="activity-view-all" onClick={onViewAll}>
            View All
          </button>
        )}
      </div>
      <div className="activity-list">
        {timeline.length === 0 ? (
          <div className="activity-empty">No recent activity</div>
        ) : (
          timeline.slice(0, 5).map((event, index) => (
            <div key={event.id || index} className="activity-item">
              <div className={`activity-icon ${getIconClass(event.event_type)}`}>
                {typeIcons[event.event_type] || '●'}
              </div>
              <div className="activity-content">
                <div className="activity-title">
                  {event.title}
                  {isNew(event.created_at) && (
                    <span className="activity-new-badge">New</span>
                  )}
                </div>
                {event.description && (
                  <div className="activity-description">{event.description}</div>
                )}
                <div className="activity-time">{getRelativeTime(event.created_at)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// Info Bar Component - Shows LO info on left, loan details on right
const PortalInfoBar = ({ loan, workspace, contacts, loanOfficerInfo }) => {
  // LO info comes from the workspace's assigned user (loan officer)
  const loName = loanOfficerInfo?.name || workspace?.assigned_user_name || 'Your Loan Officer';
  const loEmail = loanOfficerInfo?.email || workspace?.assigned_user_email || '';
  const loPhone = loanOfficerInfo?.phone || workspace?.assigned_user_phone || '';

  return (
    <div className="portal-info-bar">
      <div className="info-bar-content">
        {/* Left Side - Loan Officer Info */}
        <div className="info-bar-left">
          <div className="lo-info-section">
            <div className="lo-name">{loName}</div>
            <div className="lo-contact">
              {loEmail && (
                <a href={`mailto:${loEmail}`} className="lo-email">
                  <span className="contact-icon">✉</span> {loEmail}
                </a>
              )}
              {loPhone && (
                <a href={`tel:${loPhone}`} className="lo-phone">
                  <span className="contact-icon">📞</span> {loPhone}
                </a>
              )}
            </div>
          </div>
          <div className="property-info-section">
            <span className="property-address">{formatAddress(loan?.property_address)}</span>
          </div>
        </div>

        {/* Right Side - Loan Details */}
        <div className="info-bar-right">
          <div className="loan-detail-item">
            <span className="detail-label">Purpose</span>
            <span className="detail-value">{loan?.loan_purpose ? loan.loan_purpose.charAt(0).toUpperCase() + loan.loan_purpose.slice(1) : 'Purchase'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Loan Type</span>
            <span className="detail-value">{loan?.product_type || 'Conventional'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Term</span>
            <span className="detail-value">{loan?.loan_term || '30'} Years</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Loan Amount</span>
            <span className="detail-value highlight">{formatCurrency(loan?.loan_amount)}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Interest Rate</span>
            <span className="detail-value">{loan?.interest_rate ? `${loan.interest_rate}%` : 'TBD'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Rate Lock</span>
            <span className="detail-value">{loan?.rate_lock_date ? formatDate(loan.rate_lock_date) : 'Not Locked'}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Est. Closing</span>
            <span className="detail-value">{formatDate(loan?.target_close_date)}</span>
          </div>
          <div className="loan-detail-item">
            <span className="detail-label">Scheduled</span>
            <span className="detail-value">{loan?.closing_date ? formatDate(loan.closing_date) : 'TBD'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Loan Summary Card Component - Shows loan details at a glance
const LoanSummaryCard = ({ loan, workspace, contacts, subStage }) => {
  const borrower = contacts?.find(c => c.contact_type === 'borrower') || contacts?.[0];
  const daysLeft = daysUntilClose(loan?.target_close_date);

  return (
    <div className="loan-summary-card">
      <div className="loan-header">
        <div className="loan-type-badge">
          {loan?.product_type || loan?.loan_purpose || 'Your Loan'}
        </div>
        <StatusBadge status={subStage || workspace?.status} />
      </div>

      <div className="loan-details-grid">
        <div className="loan-detail">
          <span className="detail-label">Loan Amount</span>
          <span className="detail-value">{formatCurrency(loan?.loan_amount)}</span>
        </div>
        <div className="loan-detail">
          <span className="detail-label">Interest Rate</span>
          <span className="detail-value">{loan?.interest_rate ? `${loan.interest_rate}%` : 'TBD'}</span>
        </div>
        <div className="loan-detail">
          <span className="detail-label">Property</span>
          <span className="detail-value detail-address">{formatAddress(loan?.property_address)}</span>
        </div>
        <div className="loan-detail">
          <span className="detail-label">Expected Close</span>
          <span className="detail-value">
            {formatDate(loan?.target_close_date)}
            {daysLeft !== null && daysLeft > 0 && (
              <span className="days-badge">{daysLeft} days</span>
            )}
          </span>
        </div>
      </div>

      {!loan && (
        <div className="loan-empty-state">
          <p>Your loan details will appear here once your application is processed.</p>
        </div>
      )}
    </div>
  );
};

// Conditions Needs List Card - Shows conditions from lead_conditions table
const ConditionsNeedsListCard = ({ conditions, onViewAll, onUploadForCondition, uploading }) => {
  // Filter conditions by status
  const pendingConditions = conditions?.filter(c => c.status === 'pending') || [];
  const receivedConditions = conditions?.filter(c => c.status === 'received') || [];
  const approvedConditions = conditions?.filter(c => c.status === 'approved') || [];

  const totalConditions = (conditions || []).length;
  const completedCount = approvedConditions.length + receivedConditions.length;
  const completionPct = totalConditions > 0 ? Math.round((completedCount / totalConditions) * 100) : 0;

  // Map condition status to display status
  const getDisplayStatus = (status) => {
    const statusMap = {
      'pending': 'needed',
      'received': 'pending',
      'approved': 'done',
      'waived': 'na',
    };
    return statusMap[status] || 'needed';
  };

  const statusIcons = {
    needed: '○',
    pending: '◐',
    done: '●',
    na: '—',
  };

  const statusLabels = {
    needed: 'Document Needed',
    pending: 'Under Review',
    done: 'Approved',
    na: 'Waived',
  };

  // Category display names
  const categoryNames = {
    income_verification: 'Income',
    asset_verification: 'Assets',
    employment: 'Employment',
    property: 'Property',
    credit: 'Credit',
    other: 'Other',
  };

  // If no conditions, show empty state
  if (!conditions || conditions.length === 0) {
    return (
      <div className="document-checklist-card">
        <div className="checklist-header">
          <h3>Your Needs List</h3>
        </div>
        <div className="checklist-empty">
          <p>Your document requirements will appear here once your application is processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="document-checklist-card">
      <div className="checklist-header">
        <h3>Your Needs List</h3>
        <span className="completion-badge">{completionPct}% Complete</span>
      </div>

      <ProgressBar percentage={completionPct} label="Documents" />

      <div className="checklist-items">
        {/* Show pending conditions first (max 5) */}
        {pendingConditions.slice(0, 5).map((condition) => {
          const displayStatus = getDisplayStatus(condition.status);
          return (
            <div key={condition.id} className={`checklist-item status-${displayStatus}`}>
              <span className="checklist-icon">{statusIcons[displayStatus]}</span>
              <div className="checklist-info">
                <span className="checklist-label">
                  {condition.name}
                  {condition.is_new && <span className="new-condition-badge">NEW</span>}
                </span>
                <div className="checklist-meta">
                  <span className="checklist-category">{categoryNames[condition.category] || condition.category}</span>
                  {condition.due_date && (
                    <span className="checklist-due">Due: {new Date(condition.due_date).toLocaleDateString()}</span>
                  )}
                </div>
                {condition.description && (
                  <span className="checklist-description">{condition.description}</span>
                )}
              </div>
              <div className="checklist-actions">
                <label className="upload-condition-btn">
                  <input
                    type="file"
                    onChange={(e) => onUploadForCondition(condition.id, e)}
                    disabled={uploading}
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                  />
                  {uploading ? '...' : '↑ Upload'}
                </label>
              </div>
            </div>
          );
        })}

        {/* Show received conditions (under review) */}
        {receivedConditions.slice(0, 2).map((condition) => (
          <div key={condition.id} className="checklist-item status-pending">
            <span className="checklist-icon">{statusIcons.pending}</span>
            <div className="checklist-info">
              <span className="checklist-label">{condition.name}</span>
              <span className="checklist-category">{categoryNames[condition.category] || condition.category}</span>
            </div>
            <span className="checklist-status status-pending">{statusLabels.pending}</span>
          </div>
        ))}

        {/* Show recent approved conditions (max 2) */}
        {approvedConditions.slice(0, 2).map((condition) => (
          <div key={condition.id} className="checklist-item status-done">
            <span className="checklist-icon">{statusIcons.done}</span>
            <span className="checklist-label">{condition.name}</span>
            <span className="checklist-status status-done">{statusLabels.done}</span>
          </div>
        ))}
      </div>

      {pendingConditions.length > 5 && (
        <button className="upload-cta-btn" onClick={onViewAll}>
          View All {pendingConditions.length} Items Needed
        </button>
      )}
    </div>
  );
};

// Legacy Needs List Card - Shows tasks (fallback if no conditions)
const NeedsListCard = ({ tasks, onViewAll }) => {
  // Filter to show pending tasks (conditions that need to be completed)
  const pendingTasks = tasks?.filter(t =>
    t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS'
  ) || [];
  const completedTasks = tasks?.filter(t =>
    t.status === 'completed' || t.status === 'DONE'
  ) || [];

  const totalTasks = (tasks || []).length;
  const completedCount = completedTasks.length;
  const completionPct = totalTasks > 0 ? Math.round((completedCount / totalTasks) * 100) : 0;

  // Map task status to display status
  const getDisplayStatus = (status) => {
    const statusMap = {
      'open': 'needed',
      'TODO': 'needed',
      'IN_PROGRESS': 'pending',
      'completed': 'done',
      'DONE': 'done',
      'BLOCKED': 'blocked',
      'NA': 'na',
    };
    return statusMap[status] || 'needed';
  };

  const statusIcons = {
    needed: '○',
    pending: '◐',
    done: '●',
    blocked: '⚠',
    na: '—',
  };

  const statusLabels = {
    needed: 'Action Required',
    pending: 'In Progress',
    done: 'Complete',
    blocked: 'Blocked',
    na: 'N/A',
  };

  // If no tasks, show empty state
  if (!tasks || tasks.length === 0) {
    return (
      <div className="document-checklist-card">
        <div className="checklist-header">
          <h3>Your Needs List</h3>
        </div>
        <div className="checklist-empty">
          <p>Your task list will appear here once your application is processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="document-checklist-card">
      <div className="checklist-header">
        <h3>Your Needs List</h3>
        <span className="completion-badge">{completionPct}% Complete</span>
      </div>

      <ProgressBar percentage={completionPct} label="Tasks" />

      <div className="checklist-items">
        {/* Show pending tasks first (max 5) */}
        {pendingTasks.slice(0, 5).map((task) => {
          const displayStatus = getDisplayStatus(task.status);
          return (
            <div key={task.id} className={`checklist-item status-${displayStatus}`}>
              <span className="checklist-icon">{statusIcons[displayStatus]}</span>
              <div className="checklist-info">
                <span className="checklist-label">{task.title}</span>
                {task.due_at && (
                  <span className="checklist-due">Due: {new Date(task.due_at).toLocaleDateString()}</span>
                )}
              </div>
              <span className={`checklist-status status-${displayStatus}`}>{statusLabels[displayStatus]}</span>
            </div>
          );
        })}

        {/* Show recent completed tasks (max 2) */}
        {completedTasks.slice(0, 2).map((task) => (
          <div key={task.id} className="checklist-item status-done">
            <span className="checklist-icon">{statusIcons.done}</span>
            <span className="checklist-label">{task.title}</span>
            <span className="checklist-status status-done">{statusLabels.done}</span>
          </div>
        ))}
      </div>

      {pendingTasks.length > 5 && (
        <button className="upload-cta-btn" onClick={onViewAll}>
          View All {pendingTasks.length} Items
        </button>
      )}
    </div>
  );
};

// Quick Actions Bar - Provides quick access to common actions
const ContactLOCard = ({ onSchedule }) => (
  <div className="contact-lo-card">
    <div className="contact-lo-content">
      <h3>Questions about your loan?</h3>
      <p>Your loan officer is here to help guide you through the process.</p>
    </div>
    <button className="schedule-call-btn" onClick={onSchedule}>
      <span className="btn-icon">📅</span>
      Schedule a Call
    </button>
  </div>
);

/**
 * Active Loan Portal Component
 *
 * Props from PortalContainer:
 * - data: Complete workspace data (workspace, loan, contacts, documents, tasks, etc.)
 * - slug: Workspace slug for API calls
 * - subStage: Current sub-stage (preapproval, under_contract, processing, clear_to_close)
 * - onRefresh: Callback to refresh data from parent
 */
export default function ActiveLoanPortal({ data, slug, subStage, onRefresh }) {
  const location = useLocation();

  // Extract data from props
  const workspace = data?.workspace;
  const application = data?.application;
  const loan = data?.loan;
  const contacts = data?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];

  // Local state for mutable data
  const [documents, setDocuments] = useState(data?.documents || []);
  const [tasks, setTasks] = useState(data?.tasks || []);
  const [conditions, setConditions] = useState([]);
  const [conditionsLoading, setConditionsLoading] = useState(false);
  const [smartDocsRequirements, setSmartDocsRequirements] = useState([]);
  const [smartDocsLoading, setSmartDocsLoading] = useState(false);
  const [milestones, setMilestones] = useState(data?.milestones || []);
  const [timeline, setTimeline] = useState(data?.timeline || []);
  const [messages, setMessages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [conditionUploading, setConditionUploading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);

  // UI state
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showVideoLightbox, setShowVideoLightbox] = useState(true); // Auto-show on load
  const [videoListKey, setVideoListKey] = useState(0); // Key to force refresh video list
  const [newMessage, setNewMessage] = useState({ subject: '', body: '' });

  // Check for submission success message
  const urlParams = new URLSearchParams(location.search);
  const justSubmitted = urlParams.get('submitted') === 'true';
  const [showSubmitSuccess, setShowSubmitSuccess] = useState(justSubmitted);

  // Sync data when props change
  useEffect(() => {
    if (data) {
      setDocuments(data.documents || []);
      setTasks(data.tasks || []);
      setMilestones(data.milestones || []);
      setTimeline(data.timeline || []);
    }
  }, [data]);

  // Load conditions
  const loadConditions = useCallback(async () => {
    if (!slug) return;
    setConditionsLoading(true);
    try {
      const conditionsData = await api.getWorkspaceConditions(slug);
      setConditions(conditionsData.conditions || []);
    } catch (err) {
      console.error('Failed to load conditions:', err);
    } finally {
      setConditionsLoading(false);
    }
  }, [slug]);

  // Load conditions on mount and when slug changes
  useEffect(() => {
    loadConditions();
  }, [loadConditions]);

  // Load Smart Docs requirements
  const loadSmartDocsRequirements = useCallback(async () => {
    if (!slug) return;
    setSmartDocsLoading(true);
    try {
      const response = await fetch(`/api/portal/smart-docs/${slug}/requirements`);
      if (response.ok) {
        const data = await response.json();
        setSmartDocsRequirements(data.requirements || []);
      }
    } catch (err) {
      console.error('Failed to load Smart Docs requirements:', err);
    } finally {
      setSmartDocsLoading(false);
    }
  }, [slug]);

  // Load Smart Docs requirements on mount
  useEffect(() => {
    loadSmartDocsRequirements();
  }, [loadSmartDocsRequirements]);

  // Load messages
  const loadMessages = useCallback(async () => {
    try {
      const msgData = await api.getWorkspaceMessages(slug);
      setMessages(msgData.messages || []);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }, [slug]);

  // Load messages when tab changes to messages
  useEffect(() => {
    if (activeTab === 'messages') {
      loadMessages();
    }
  }, [activeTab, loadMessages]);

  // Handle document download
  const handleDownload = async (documentId) => {
    try {
      const downloadData = await api.getDocumentDownload(documentId, workspace?.id);
      window.open(downloadData.download_url, '_blank');
    } catch (err) {
      console.error('Download failed:', err);
      toast.error('Failed to download document');
    }
  };

  // Handle document upload
  const handleUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      for (const file of files) {
        try {
          // Try S3 presigned URL upload first
          try {
            const uploadData = await api.getDocumentUploadUrl(slug, {
              filename: file.name,
              contentType: file.type,
            });

            // Upload to S3
            const s3Response = await fetch(uploadData.upload_url, {
              method: 'PUT',
              body: file,
              headers: {
                'Content-Type': file.type,
              },
            });

            if (!s3Response.ok) {
              throw new Error(`S3 upload failed: ${s3Response.status}`);
            }

            // Complete upload
            await api.completeDocumentUpload(slug, {
              documentKey: uploadData.document_key,
              filename: file.name,
              fileSize: file.size,
              contentType: file.type,
            });
          } catch (s3Error) {
            console.warn('S3 upload failed, trying direct upload:', s3Error);
            // Fallback to direct upload
            await api.uploadDocumentDirect(slug, file);
          }

          // Refresh documents
          const docsData = await api.getWorkspaceDocuments(slug);
          setDocuments(docsData.documents || []);
        } catch (err) {
          console.error('Upload failed:', err);
          toast.error(`Failed to upload ${file.name}: ${err.message || 'Unknown error'}`);
        }
      }
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  // Handle document upload for a specific condition
  const handleUploadForCondition = async (conditionId, event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setConditionUploading(true);
    try {
      for (const file of files) {
        try {
          // Try S3 presigned URL upload first
          try {
            const uploadData = await api.getDocumentUploadUrl(slug, {
              filename: file.name,
              contentType: file.type,
              documentType: `condition_${conditionId}`,
            });

            // Upload to S3
            const s3Response = await fetch(uploadData.upload_url, {
              method: 'PUT',
              body: file,
              headers: {
                'Content-Type': file.type,
              },
            });

            if (!s3Response.ok) {
              throw new Error(`S3 upload failed: ${s3Response.status}`);
            }

            // Complete upload
            await api.completeDocumentUpload(slug, {
              documentKey: uploadData.document_key,
              filename: file.name,
              fileSize: file.size,
              contentType: file.type,
              documentType: `condition_${conditionId}`,
            });
          } catch (s3Error) {
            console.warn('S3 upload failed, trying direct upload:', s3Error);
            // Fallback to direct upload
            await api.uploadDocumentDirect(slug, file, `condition_${conditionId}`);
          }

          // Mark condition as received
          await api.markConditionReceived(slug, conditionId);

          // Refresh conditions and documents
          await loadConditions();
          const docsData = await api.getWorkspaceDocuments(slug);
          setDocuments(docsData.documents || []);
        } catch (err) {
          console.error('Upload failed:', err);
          toast.error(`Failed to upload ${file.name}: ${err.message || 'Unknown error'}`);
        }
      }
    } finally {
      setConditionUploading(false);
      event.target.value = '';
    }
  };

  // Handle task completion
  const handleTaskComplete = async (taskId, complete) => {
    try {
      await api.updateTask(slug, taskId, {
        status: complete ? 'completed' : 'open',
      });

      // Refresh tasks
      const tasksData = await api.getWorkspaceTasks(slug);
      setTasks(tasksData.tasks || []);
    } catch (err) {
      console.error('Failed to update task:', err);
      toast.error('Failed to update task');
    }
  };

  // Handle send message
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!newMessage.body.trim()) return;

    setSendingMessage(true);
    try {
      await api.sendMessage(slug, {
        content: newMessage.body,
        messageType: 'text',
      });
      setNewMessage({ subject: '', body: '' });
      loadMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
      toast.error('Failed to send message');
    } finally {
      setSendingMessage(false);
    }
  };

  // Calculate counts for badges
  const pendingTasksCount = tasks.filter(t => t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS').length;
  const unreadMessagesCount = messages.filter(m => !m.is_read && m.direction === 'outbound').length;

  // Get borrower name for greeting
  const borrowerName = borrower
    ? `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim()
    : 'Welcome';

  return (
    <div className="purl-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-content">
          {/* Info Bar with LO Info (left) and Loan Details (right) */}
          <PortalInfoBar
            loan={loan}
            workspace={workspace}
            contacts={contacts}
            loanOfficerInfo={data?.loanOfficer}
          />

          {/* Milestone Progress Indicator - Uses actual CRM lead stage */}
          <HeaderMilestoneProgress
            subStage={subStage}
            workspaceStatus={workspace?.status}
            leadStage={data?.lead?.stage}
          />
        </div>
      </header>

      {/* Success Message Banner */}
      {showSubmitSuccess && (
        <div className="submit-success-banner">
          <div className="banner-content">
            <span className="banner-icon">✓</span>
            <div className="banner-text">
              <strong>Application Submitted Successfully!</strong>
              <p>Your loan officer will review your application and be in touch soon.</p>
            </div>
            <button className="banner-close" onClick={() => setShowSubmitSuccess(false)}>×</button>
          </div>
        </div>
      )}

      {/* Navigation Tabs - Arrow/chevron style */}
      <nav className="portal-nav chevron-tabs">
        <TabButton
          label="Overview"
          isActive={activeTab === 'overview'}
          onClick={() => setActiveTab('overview')}
          isFirst={true}
        />
        <TabButton
          label="Application"
          isActive={activeTab === 'application'}
          onClick={() => setActiveTab('application')}
        />
        <TabButton
          label="Documents"
          isActive={activeTab === 'documents'}
          onClick={() => setActiveTab('documents')}
          badgeCount={conditions.filter(c => c.is_new && c.status === 'pending').length}
        />
        <TabButton
          label="Loan Comparison"
          isActive={activeTab === 'loan-quote'}
          onClick={() => setActiveTab('loan-quote')}
          hasNotification={data?.loanEstimates?.length > 0}
        />
        <TabButton
          label="Pre-Approval"
          isActive={activeTab === 'pre-approval'}
          onClick={() => setActiveTab('pre-approval')}
          hasNotification={data?.preApprovalLetter != null}
        />
        <TabButton
          label="Contacts"
          isActive={activeTab === 'contacts'}
          onClick={() => setActiveTab('contacts')}
          isLast={true}
        />
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            <div className="portal-dashboard-layout">
              {/* Main Content Area */}
              <div className="portal-main-content">
                {/* Contact Your Loan Officer - Now at the top */}
                <ContactLOCard onSchedule={() => setShowScheduleModal(true)} />

                {/* Video Messages from Loan Officer - Hidden when lightbox is open */}
                {!showVideoLightbox && (
                  <PortalVideoMessages
                    key={`video-messages-${videoListKey}`}
                    portalType="client"
                    identifier={slug}
                    title="Messages from Your Loan Officer"
                  />
                )}

                {/* Applicant Tasks Section - Your Action Items */}
                <ApplicantTasks
                  workspaceId={workspace?.id}
                  conditions={conditions}
                  documentRequirements={smartDocsRequirements}
                  onUploadForCondition={handleUploadForCondition}
                  uploading={conditionUploading}
                />

                {/* What's Next Section - Only show if there are additional conditions beyond applicant tasks */}
                {conditions.length > 0 && (
                  <section className="whats-next-section">
                    <h2>Documents Needed</h2>
                    <ConditionsNeedsListCard
                      conditions={conditions}
                      onViewAll={() => setActiveTab('documents')}
                      onUploadForCondition={handleUploadForCondition}
                      uploading={conditionUploading}
                    />
                  </section>
                )}

                {/* Loan Progress - Only show if there are milestones */}
                {milestones.length > 0 && (
                  <section className="progress-section">
                    <h2>Loan Progress</h2>
                    <MilestoneTracker milestones={milestones} />
                  </section>
                )}
              </div>

              {/* Sidebar */}
              <div className="portal-sidebar">
                {/* Company Logo */}
                {data?.loanOfficer?.company_logo_url && (
                  <div className="sidebar-logo-card">
                    <img
                      src={data.loanOfficer.company_logo_url}
                      alt="Company Logo"
                      className="sidebar-company-logo"
                    />
                  </div>
                )}

                {/* Days Until Closing Counter */}
                <DaysCounterCard
                  closeDate={loan?.closing_date}
                  estimatedCloseDate={loan?.target_close_date}
                />

                {/* Recent Activity */}
                <RecentActivitySidebar
                  timeline={timeline}
                  onViewAll={() => setActiveTab('timeline')}
                />
              </div>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="tab-content documents-tab">
            <div className="documents-header">
              <h2>Your Documents</h2>
              <label className="upload-btn">
                <input
                  type="file"
                  multiple
                  onChange={handleUpload}
                  disabled={uploading}
                  accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                />
                {uploading ? 'Uploading...' : '+ Upload Document'}
              </label>
            </div>

            {/* Smart Docs Requirements - Documents needed from application */}
            {slug && (
              <div className="documents-requirements-section">
                <PortalDocumentRequirements
                  workspaceSlug={slug}
                  onProgressUpdate={(progress) => {
                    // Could update parent state if needed
                    console.log('Document progress:', progress);
                  }}
                />
              </div>
            )}

            {/* Uploaded Documents */}
            <div className="uploaded-documents-section">
              <h3>Uploaded Documents</h3>
              <DocumentsTable documents={documents} onDownload={handleDownload} />
            </div>
          </div>
        )}

        {/* Application Tab */}
        {activeTab === 'application' && (
          <div className="tab-content application-tab">
            <div className="application-header">
              <h2>Your Application</h2>
            </div>
            <div className="application-summary-card">
              <div className="application-status">
                <span className="status-label">Application Status</span>
                <StatusBadge status={subStage || workspace?.status} />
              </div>
              <div className="application-details-grid">
                <div className="app-detail">
                  <span className="detail-label">Submitted</span>
                  <span className="detail-value">
                    {application?.submitted_at ? formatDate(application.submitted_at) : 'Pending'}
                  </span>
                </div>
                <div className="app-detail">
                  <span className="detail-label">Loan Purpose</span>
                  <span className="detail-value">{loan?.loan_purpose ? loan.loan_purpose.charAt(0).toUpperCase() + loan.loan_purpose.slice(1) : 'Purchase'}</span>
                </div>
                <div className="app-detail">
                  <span className="detail-label">Property Type</span>
                  <span className="detail-value">{loan?.property_type || 'Single Family'}</span>
                </div>
                <div className="app-detail">
                  <span className="detail-label">Occupancy</span>
                  <span className="detail-value">{loan?.occupancy_type || 'Primary Residence'}</span>
                </div>
              </div>
            </div>

            {/* Application Data Sections */}
            {application?.data ? (
              <div className="application-data-sections">
                {/* Personal Information */}
                {(application.data.borrower || application.data.personal) && (
                  <div className="app-section">
                    <h3 className="section-title">Personal Information</h3>
                    <div className="section-grid">
                      {application.data.borrower?.firstName && (
                        <div className="field-item">
                          <span className="field-label">First Name</span>
                          <span className="field-value">{application.data.borrower.firstName}</span>
                        </div>
                      )}
                      {application.data.borrower?.lastName && (
                        <div className="field-item">
                          <span className="field-label">Last Name</span>
                          <span className="field-value">{application.data.borrower.lastName}</span>
                        </div>
                      )}
                      {application.data.borrower?.email && (
                        <div className="field-item">
                          <span className="field-label">Email</span>
                          <span className="field-value">{application.data.borrower.email}</span>
                        </div>
                      )}
                      {application.data.borrower?.phone && (
                        <div className="field-item">
                          <span className="field-label">Phone</span>
                          <span className="field-value">{application.data.borrower.phone}</span>
                        </div>
                      )}
                      {application.data.borrower?.dateOfBirth && (
                        <div className="field-item">
                          <span className="field-label">Date of Birth</span>
                          <span className="field-value">{application.data.borrower.dateOfBirth}</span>
                        </div>
                      )}
                      {application.data.borrower?.ssn && (
                        <div className="field-item">
                          <span className="field-label">SSN</span>
                          <span className="field-value">***-**-{application.data.borrower.ssn.slice(-4)}</span>
                        </div>
                      )}
                      {application.data.borrower?.maritalStatus && (
                        <div className="field-item">
                          <span className="field-label">Marital Status</span>
                          <span className="field-value">{application.data.borrower.maritalStatus}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Current Address */}
                {application.data.borrower?.currentAddress && (
                  <div className="app-section">
                    <h3 className="section-title">Current Address</h3>
                    <div className="section-grid">
                      {application.data.borrower.currentAddress.street && (
                        <div className="field-item full-width">
                          <span className="field-label">Street Address</span>
                          <span className="field-value">{application.data.borrower.currentAddress.street}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.city && (
                        <div className="field-item">
                          <span className="field-label">City</span>
                          <span className="field-value">{application.data.borrower.currentAddress.city}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.state && (
                        <div className="field-item">
                          <span className="field-label">State</span>
                          <span className="field-value">{application.data.borrower.currentAddress.state}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.zip && (
                        <div className="field-item">
                          <span className="field-label">ZIP Code</span>
                          <span className="field-value">{application.data.borrower.currentAddress.zip}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.yearsAtAddress && (
                        <div className="field-item">
                          <span className="field-label">Years at Address</span>
                          <span className="field-value">{application.data.borrower.currentAddress.yearsAtAddress}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.housingStatus && (
                        <div className="field-item">
                          <span className="field-label">Housing Status</span>
                          <span className="field-value">{application.data.borrower.currentAddress.housingStatus}</span>
                        </div>
                      )}
                      {application.data.borrower.currentAddress.monthlyPayment && (
                        <div className="field-item">
                          <span className="field-label">Monthly Payment</span>
                          <span className="field-value">{formatCurrency(application.data.borrower.currentAddress.monthlyPayment)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Employment Information */}
                {application.data.employment && (
                  <div className="app-section">
                    <h3 className="section-title">Employment Information</h3>
                    <div className="section-grid">
                      {application.data.employment.employmentStatus && (
                        <div className="field-item">
                          <span className="field-label">Employment Status</span>
                          <span className="field-value">{application.data.employment.employmentStatus}</span>
                        </div>
                      )}
                      {application.data.employment.employerName && (
                        <div className="field-item">
                          <span className="field-label">Employer Name</span>
                          <span className="field-value">{application.data.employment.employerName}</span>
                        </div>
                      )}
                      {application.data.employment.jobTitle && (
                        <div className="field-item">
                          <span className="field-label">Job Title</span>
                          <span className="field-value">{application.data.employment.jobTitle}</span>
                        </div>
                      )}
                      {application.data.employment.yearsEmployed && (
                        <div className="field-item">
                          <span className="field-label">Years Employed</span>
                          <span className="field-value">{application.data.employment.yearsEmployed}</span>
                        </div>
                      )}
                      {application.data.employment.monthlyIncome && (
                        <div className="field-item">
                          <span className="field-label">Monthly Income</span>
                          <span className="field-value">{formatCurrency(application.data.employment.monthlyIncome)}</span>
                        </div>
                      )}
                      {application.data.employment.employerPhone && (
                        <div className="field-item">
                          <span className="field-label">Employer Phone</span>
                          <span className="field-value">{application.data.employment.employerPhone}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Property Information */}
                {application.data.property && (
                  <div className="app-section">
                    <h3 className="section-title">Subject Property</h3>
                    <div className="section-grid">
                      {application.data.property.address && (
                        <div className="field-item full-width">
                          <span className="field-label">Property Address</span>
                          <span className="field-value">{application.data.property.address}</span>
                        </div>
                      )}
                      {application.data.property.propertyType && (
                        <div className="field-item">
                          <span className="field-label">Property Type</span>
                          <span className="field-value">{application.data.property.propertyType}</span>
                        </div>
                      )}
                      {application.data.property.occupancyType && (
                        <div className="field-item">
                          <span className="field-label">Occupancy Type</span>
                          <span className="field-value">{application.data.property.occupancyType}</span>
                        </div>
                      )}
                      {application.data.property.purchasePrice && (
                        <div className="field-item">
                          <span className="field-label">Purchase Price</span>
                          <span className="field-value">{formatCurrency(application.data.property.purchasePrice)}</span>
                        </div>
                      )}
                      {application.data.property.estimatedValue && (
                        <div className="field-item">
                          <span className="field-label">Estimated Value</span>
                          <span className="field-value">{formatCurrency(application.data.property.estimatedValue)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Loan Information */}
                {application.data.loan && (
                  <div className="app-section">
                    <h3 className="section-title">Loan Details</h3>
                    <div className="section-grid">
                      {application.data.loan.loanPurpose && (
                        <div className="field-item">
                          <span className="field-label">Loan Purpose</span>
                          <span className="field-value">{application.data.loan.loanPurpose}</span>
                        </div>
                      )}
                      {application.data.loan.loanAmount && (
                        <div className="field-item">
                          <span className="field-label">Loan Amount</span>
                          <span className="field-value">{formatCurrency(application.data.loan.loanAmount)}</span>
                        </div>
                      )}
                      {application.data.loan.downPayment && (
                        <div className="field-item">
                          <span className="field-label">Down Payment</span>
                          <span className="field-value">{formatCurrency(application.data.loan.downPayment)}</span>
                        </div>
                      )}
                      {application.data.loan.loanType && (
                        <div className="field-item">
                          <span className="field-label">Loan Type</span>
                          <span className="field-value">{application.data.loan.loanType}</span>
                        </div>
                      )}
                      {application.data.loan.loanTerm && (
                        <div className="field-item">
                          <span className="field-label">Loan Term</span>
                          <span className="field-value">{application.data.loan.loanTerm} Years</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Assets */}
                {application.data.assets && (
                  <div className="app-section">
                    <h3 className="section-title">Assets</h3>
                    <div className="section-grid">
                      {application.data.assets.checkingBalance && (
                        <div className="field-item">
                          <span className="field-label">Checking Account</span>
                          <span className="field-value">{formatCurrency(application.data.assets.checkingBalance)}</span>
                        </div>
                      )}
                      {application.data.assets.savingsBalance && (
                        <div className="field-item">
                          <span className="field-label">Savings Account</span>
                          <span className="field-value">{formatCurrency(application.data.assets.savingsBalance)}</span>
                        </div>
                      )}
                      {application.data.assets.retirementBalance && (
                        <div className="field-item">
                          <span className="field-label">Retirement Accounts</span>
                          <span className="field-value">{formatCurrency(application.data.assets.retirementBalance)}</span>
                        </div>
                      )}
                      {application.data.assets.otherAssets && (
                        <div className="field-item">
                          <span className="field-label">Other Assets</span>
                          <span className="field-value">{formatCurrency(application.data.assets.otherAssets)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Declarations */}
                {application.data.declarations && (
                  <div className="app-section">
                    <h3 className="section-title">Declarations</h3>
                    <div className="declarations-list">
                      {Object.entries(application.data.declarations).map(([key, value]) => (
                        <div key={key} className="declaration-item">
                          <span className="declaration-question">
                            {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                          </span>
                          <span className={`declaration-answer ${value === true || value === 'yes' ? 'yes' : 'no'}`}>
                            {value === true || value === 'yes' ? 'Yes' : value === false || value === 'no' ? 'No' : String(value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Display any other fields not in standard sections */}
                {Object.keys(application.data).filter(key =>
                  !['borrower', 'employment', 'property', 'loan', 'assets', 'declarations', 'personal', 'coBorrower'].includes(key)
                ).length > 0 && (
                  <div className="app-section">
                    <h3 className="section-title">Additional Information</h3>
                    <div className="section-grid">
                      {Object.entries(application.data)
                        .filter(([key]) => !['borrower', 'employment', 'property', 'loan', 'assets', 'declarations', 'personal', 'coBorrower'].includes(key))
                        .map(([key, value]) => {
                          if (typeof value === 'object' && value !== null) return null;
                          return (
                            <div key={key} className="field-item">
                              <span className="field-label">
                                {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                              </span>
                              <span className="field-value">{String(value)}</span>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="application-empty-card">
                <p>Your application details will appear here once submitted.</p>
              </div>
            )}
          </div>
        )}

        {/* Loan Quote Tab - Uses TotalCostAnalysis component for comprehensive cost comparison */}
        {activeTab === 'loan-quote' && (
          <div className="tab-content loan-quote-tab">
            {data?.presentation || data?.loanEstimates?.length > 0 ? (
              <TotalCostAnalysis
                currentLoanBalance={loan?.loan_amount || 400000}
                currentRate={loan?.interest_rate || 6.5}
                currentMonthlyPayment={loan?.monthly_payment || 2528}
                currentRemainingMonths={loan?.remaining_months || 348}
                homeValue={loan?.property_value || loan?.appraisal_value || loan?.purchase_price || 550000}
                proposedScenarios={data?.presentation?.scenarios || data?.loanEstimates?.map((est, idx) => ({
                  id: est.id || `estimate-${idx}`,
                  name: est.lender_name || `Option ${idx + 1}`,
                  type: idx === 0 ? 'current' : 'refinance',
                  loanAmount: est.loan_amount || loan?.loan_amount,
                  rate: est.interest_rate || loan?.interest_rate,
                  term: est.term || 30,
                  monthlyPayment: est.monthly_payment,
                  closingCosts: est.closing_costs || est.cash_to_close || 0,
                  cashOut: est.cash_out || 0,
                })) || []}
                clientName={borrower ? `${borrower.first_name || ''} ${borrower.last_name || ''}`.trim() : 'Valued Client'}
                onScheduleCall={() => setShowScheduleModal(true)}
              />
            ) : (
              <div className="empty-state-card">
                <div className="empty-icon">💰</div>
                <h3>No Loan Comparisons Yet</h3>
                <p>Your loan officer will prepare a comprehensive cost analysis for you. This will include:</p>
                <ul className="quote-benefits-list">
                  <li>Side-by-side loan scenario comparisons</li>
                  <li>Monthly payment breakdown</li>
                  <li>Closing costs analysis</li>
                  <li>Breakeven calculations</li>
                  <li>Long-term savings projections</li>
                </ul>
                <p>Check back soon or contact your loan officer for more information.</p>
                <button className="schedule-call-btn" onClick={() => setShowScheduleModal(true)}>
                  <span className="btn-icon">📅</span>
                  Schedule a Call to Discuss Options
                </button>
              </div>
            )}
          </div>
        )}

        {/* Pre-Approval Tab */}
        {activeTab === 'pre-approval' && (
          <div className="tab-content pre-approval-tab">
            <div className="pre-approval-header">
              <h2>Pre-Approval Status</h2>
            </div>
            {data?.preApprovalLetter ? (
              <div className="pre-approval-card">
                <div className="pre-approval-status success">
                  <span className="status-icon">✓</span>
                  <span className="status-text">You're Pre-Approved!</span>
                </div>
                <div className="pre-approval-details">
                  <div className="approval-item">
                    <span className="item-label">Approved Amount</span>
                    <span className="item-value highlight">{formatCurrency(data.preApprovalLetter.amount)}</span>
                  </div>
                  <div className="approval-item">
                    <span className="item-label">Issue Date</span>
                    <span className="item-value">{formatDate(data.preApprovalLetter.issued_at)}</span>
                  </div>
                  <div className="approval-item">
                    <span className="item-label">Expires</span>
                    <span className="item-value">{formatDate(data.preApprovalLetter.expires_at)}</span>
                  </div>
                </div>
                <button className="download-letter-btn" onClick={() => window.open(data.preApprovalLetter.download_url, '_blank')}>
                  Download Pre-Approval Letter
                </button>
              </div>
            ) : (
              <div className="pre-approval-pending">
                <div className="pending-icon">⏳</div>
                <h3>Pre-Approval In Progress</h3>
                <p>Your pre-approval letter will be available here once your loan officer completes the review.</p>
                <div className="pre-approval-steps">
                  <div className={`step ${subStage === 'application' || !subStage ? 'current' : 'complete'}`}>
                    <span className="step-number">1</span>
                    <span className="step-text">Application Review</span>
                  </div>
                  <div className={`step ${subStage === 'docs_requested' ? 'current' : subStage === 'docs_approved' || subStage === 'pre_approved' ? 'complete' : ''}`}>
                    <span className="step-number">2</span>
                    <span className="step-text">Document Verification</span>
                  </div>
                  <div className={`step ${subStage === 'pre_approved' ? 'complete' : ''}`}>
                    <span className="step-number">3</span>
                    <span className="step-text">Pre-Approval Issued</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Contacts Tab */}
        {activeTab === 'contacts' && (
          <div className="tab-content contacts-tab">
            <div className="contacts-header">
              <h2>Your Loan Team</h2>
            </div>
            <div className="contacts-grid">
              {/* Loan Officer */}
              <div className="contact-card primary">
                <div className="contact-avatar">
                  {getInitials(data?.loanOfficer?.name || workspace?.assigned_user_name || 'LO')}
                </div>
                <div className="contact-info">
                  <span className="contact-role">Loan Officer</span>
                  <span className="contact-name">{data?.loanOfficer?.name || workspace?.assigned_user_name || 'Your Loan Officer'}</span>
                  {(data?.loanOfficer?.email || workspace?.assigned_user_email) && (
                    <a href={`mailto:${data?.loanOfficer?.email || workspace?.assigned_user_email}`} className="contact-email">
                      {data?.loanOfficer?.email || workspace?.assigned_user_email}
                    </a>
                  )}
                  {(data?.loanOfficer?.phone || workspace?.assigned_user_phone) && (
                    <a href={`tel:${data?.loanOfficer?.phone || workspace?.assigned_user_phone}`} className="contact-phone">
                      {data?.loanOfficer?.phone || workspace?.assigned_user_phone}
                    </a>
                  )}
                </div>
                <button className="contact-action-btn" onClick={() => setShowScheduleModal(true)}>
                  Schedule a Call
                </button>
              </div>

              {/* Additional team members from contacts */}
              {contacts.filter(c => c.contact_type !== 'borrower').map(contact => (
                <div key={contact.id} className="contact-card">
                  <div className="contact-avatar">
                    {getInitials(`${contact.first_name || ''} ${contact.last_name || ''}`)}
                  </div>
                  <div className="contact-info">
                    <span className="contact-role">{contact.contact_type?.replace('_', ' ') || 'Team Member'}</span>
                    <span className="contact-name">{`${contact.first_name || ''} ${contact.last_name || ''}`.trim()}</span>
                    {contact.email && (
                      <a href={`mailto:${contact.email}`} className="contact-email">{contact.email}</a>
                    )}
                    {contact.phone && (
                      <a href={`tel:${contact.phone}`} className="contact-phone">{contact.phone}</a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Schedule Appointment Modal */}
      <ScheduleAppointmentModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onSuccess={() => {
          setShowScheduleModal(false);
          // Could show a success message here
        }}
        borrower={borrower ? {
          id: borrower.id,
          first_name: borrower.first_name,
          last_name: borrower.last_name,
          email: borrower.email,
          phone: borrower.phone,
        } : null}
      />

      {/* Video Lightbox - Auto-opens when user has unwatched videos */}
      {showVideoLightbox && slug && (
        <VideoLightbox
          portalType="client"
          identifier={slug}
          onClose={() => setShowVideoLightbox(false)}
          onVideoWatched={() => {
            // Video was watched and deleted, refresh the portal video list
            setShowVideoLightbox(false);
            setVideoListKey(prev => prev + 1); // Force PortalVideoMessages to re-fetch
          }}
        />
      )}

      {/* Footer */}
      <footer className="portal-footer">
        <p>Secure Borrower Portal</p>
        <p className="footer-contact">
          Need help? Contact your loan officer directly.
        </p>
      </footer>
    </div>
  );
}
