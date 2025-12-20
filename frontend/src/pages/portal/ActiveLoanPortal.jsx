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
import '../PURLPortal.css';

// Tab components
const TabButton = ({ label, icon, isActive, onClick, badge }) => (
  <button
    className={`purl-tab-btn ${isActive ? 'active' : ''}`}
    onClick={onClick}
  >
    <span className="tab-icon">{icon}</span>
    <span className="tab-label">{label}</span>
    {badge > 0 && <span className="tab-badge">{badge}</span>}
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
  // Determine if we're in the lead/pre-approval phase or active loan phase
  const status = subStage || workspaceStatus || '';
  const statusLower = status?.toLowerCase() || '';

  // Check if we're in the lead stage (pre-approval journey)
  // Lead stages: new, contacted, qualified, application, pre_qualified, pre_approved
  const isLeadStage = [
    'lead', 'new', 'contacted', 'qualified', 'application',
    'pre_qualified', 'pre_approved', 'preapproval', 'active'
  ].includes(statusLower) || leadStage;

  // Define lead journey milestones (matches CRM Lead stages)
  const leadStages = [
    { id: 'application_completed', label: 'Application Completed', shortLabel: 'App Completed' },
    { id: 'document_fulfillment', label: 'Document Fulfillment', shortLabel: 'Doc Fulfillment' },
    { id: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre-Approved' },
  ];

  // Define full loan journey stages (after pre-approval)
  const loanStages = [
    { id: 'processing', label: 'Processing', shortLabel: 'Processing' },
    { id: 'underwriting', label: 'Underwriting', shortLabel: 'Underwriting' },
    { id: 'approval', label: 'Approval', shortLabel: 'Approved' },
    { id: 'clear_to_close', label: 'Clear to Close', shortLabel: 'CTC' },
    { id: 'closing', label: 'Closing', shortLabel: 'Closing' },
  ];

  // Use appropriate stages based on current phase
  const stages = isLeadStage ? leadStages : loanStages;

  // Determine current stage index based on status
  const getCurrentStageIndex = () => {
    if (isLeadStage) {
      // Lead stage mapping:
      // Application Completed (0) - always complete when portal exists (application was submitted)
      // Document Fulfillment (1) - Pre-Qualified in CRM
      // Pre-Approved (2) - Pre-Approved in CRM
      const leadStatusToIndex = {
        'new': 1,           // Application completed, working on documents
        'contacted': 1,     // Application completed, working on documents
        'qualified': 1,     // Application completed, working on documents
        'application': 1,   // Application completed, working on documents
        'lead': 1,          // Application completed, working on documents
        'active': 1,        // Application completed, working on documents
        'preapproval': 1,   // Application completed, working on documents
        'pre_qualified': 2, // Documents done, working on pre-approval
        'pre_approved': 3,  // All complete
      };
      return leadStatusToIndex[statusLower] ?? 1; // Default: application complete
    } else {
      // Full loan process mapping
      const loanStatusToIndex = {
        'processing': 0,
        'underwriting': 1,
        'conditional_approval': 2,
        'approved': 2,
        'approval': 2,
        'clear_to_close': 3,
        'ctc': 3,
        'closing': 4,
        'docs_out': 4,
        'docs_back': 4,
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
const DocumentCard = ({ document, onDownload }) => {
  const statusIcons = {
    pending: '⏳',
    approved: '✓',
    rejected: '✗'
  };

  return (
    <div className={`document-card status-${document.status}`}>
      <div className="doc-icon">📄</div>
      <div className="doc-info">
        <div className="doc-name">{document.filename}</div>
        <div className="doc-meta">
          {document.document_type && <span>{document.document_type}</span>}
          <span>{new Date(document.uploaded_at).toLocaleDateString()}</span>
        </div>
      </div>
      <div className="doc-status">
        <span className="status-icon">{statusIcons[document.status]}</span>
        <button className="download-btn" onClick={() => onDownload(document.id)}>
          ↓
        </button>
      </div>
    </div>
  );
};

// Task card component
const TaskCard = ({ task, onComplete }) => {
  const priorityColors = {
    high: 'red',
    medium: 'yellow',
    low: 'green'
  };

  const isOverdue = task.due_at && new Date(task.due_at) < new Date();

  return (
    <div className={`task-card ${task.status === 'completed' ? 'completed' : ''} ${isOverdue ? 'overdue' : ''}`}>
      <div className="task-checkbox">
        <input
          type="checkbox"
          checked={task.status === 'completed'}
          onChange={() => onComplete(task.id, task.status !== 'completed')}
          disabled={task.status === 'completed'}
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
          <span className={`priority priority-${priorityColors[task.priority]}`}>
            {task.priority}
          </span>
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
  const [milestones, setMilestones] = useState(data?.milestones || []);
  const [timeline, setTimeline] = useState(data?.timeline || []);
  const [messages, setMessages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [conditionUploading, setConditionUploading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);

  // UI state
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
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
      alert('Failed to download document');
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
          // Get upload URL
          const uploadData = await api.getDocumentUploadUrl(slug, {
            filename: file.name,
            contentType: file.type,
          });

          // Upload to S3
          await fetch(uploadData.upload_url, {
            method: 'PUT',
            body: file,
            headers: {
              'Content-Type': file.type,
            },
          });

          // Complete upload
          await api.completeDocumentUpload(slug, {
            documentKey: uploadData.document_key,
            filename: file.name,
            fileSize: file.size,
            contentType: file.type,
          });

          // Refresh documents
          const docsData = await api.getWorkspaceDocuments(slug);
          setDocuments(docsData.documents || []);
        } catch (err) {
          console.error('Upload failed:', err);
          alert(`Failed to upload ${file.name}`);
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
          // Get upload URL
          const uploadData = await api.getDocumentUploadUrl(slug, {
            filename: file.name,
            contentType: file.type,
            documentType: `condition_${conditionId}`,
          });

          // Upload to S3
          await fetch(uploadData.upload_url, {
            method: 'PUT',
            body: file,
            headers: {
              'Content-Type': file.type,
            },
          });

          // Complete upload
          await api.completeDocumentUpload(slug, {
            documentKey: uploadData.document_key,
            filename: file.name,
            fileSize: file.size,
            contentType: file.type,
            documentType: `condition_${conditionId}`,
          });

          // Mark condition as received
          await api.markConditionReceived(slug, conditionId);

          // Refresh conditions and documents
          await loadConditions();
          const docsData = await api.getWorkspaceDocuments(slug);
          setDocuments(docsData.documents || []);
        } catch (err) {
          console.error('Upload failed:', err);
          alert(`Failed to upload ${file.name}`);
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
      alert('Failed to update task');
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
      alert('Failed to send message');
    } finally {
      setSendingMessage(false);
    }
  };

  // Calculate counts for badges
  const pendingTasksCount = tasks.filter(t => t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS').length;
  const unreadMessagesCount = messages.filter(m => !m.is_read && m.direction === 'outbound').length;

  return (
    <div className="purl-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-content">
          <div className="workspace-info">
            <h1>{workspace?.display_name || 'Your Loan Portal'}</h1>
          </div>
          {/* Milestone Progress Indicator */}
          <HeaderMilestoneProgress
            subStage={subStage}
            workspaceStatus={workspace?.status}
            leadStage={workspace?.lead_stage || data?.lead?.stage}
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

      {/* Navigation Tabs */}
      <nav className="portal-nav">
        <TabButton
          label="Overview"
          icon="🏠"
          isActive={activeTab === 'overview'}
          onClick={() => setActiveTab('overview')}
        />
        <TabButton
          label="Documents"
          icon="📄"
          isActive={activeTab === 'documents'}
          onClick={() => setActiveTab('documents')}
          badge={documents.filter(d => d.status === 'pending').length}
        />
        <TabButton
          label="Tasks"
          icon="✓"
          isActive={activeTab === 'tasks'}
          onClick={() => setActiveTab('tasks')}
          badge={pendingTasksCount}
        />
        <TabButton
          label="Timeline"
          icon="📅"
          isActive={activeTab === 'timeline'}
          onClick={() => setActiveTab('timeline')}
        />
        <TabButton
          label="Messages"
          icon="💬"
          isActive={activeTab === 'messages'}
          onClick={() => setActiveTab('messages')}
          badge={unreadMessagesCount}
        />
        <TabButton
          label="Calculator"
          icon="🧮"
          isActive={activeTab === 'calculator'}
          onClick={() => setActiveTab('calculator')}
        />
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            {/* Loan Summary Card */}
            <LoanSummaryCard loan={loan} workspace={workspace} contacts={contacts} subStage={subStage} />

            {/* What's Next Section - Only show if there are tasks or conditions */}
            {(conditions.length > 0 || tasks.filter(t => t.status === 'open' || t.status === 'TODO').length > 0) && (
              <section className="whats-next-section">
                <h2>What's Next</h2>
                {conditions.length > 0 ? (
                  <ConditionsNeedsListCard
                    conditions={conditions}
                    onViewAll={() => setActiveTab('tasks')}
                    onUploadForCondition={handleUploadForCondition}
                    uploading={conditionUploading}
                  />
                ) : (
                  <div className="pending-tasks-list">
                    {tasks.filter(t => t.status === 'open' || t.status === 'TODO').slice(0, 3).map(task => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        onComplete={handleTaskComplete}
                      />
                    ))}
                    {pendingTasksCount > 3 && (
                      <button className="view-all-btn" onClick={() => setActiveTab('tasks')}>
                        View all {pendingTasksCount} tasks →
                      </button>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* All Caught Up Message - Show when no pending items */}
            {conditions.length === 0 && tasks.filter(t => t.status === 'open' || t.status === 'TODO').length === 0 && (
              <section className="all-caught-up-section">
                <div className="caught-up-icon">✓</div>
                <h2>You're all caught up!</h2>
                <p>Your loan officer is reviewing your application. We'll notify you when there's something new.</p>
              </section>
            )}

            {/* Loan Progress - Only show if there are milestones */}
            {milestones.length > 0 && (
              <section className="progress-section">
                <h2>Loan Progress</h2>
                <MilestoneTracker milestones={milestones} />
              </section>
            )}

            {/* Recent Activity - Only show if there's activity */}
            {timeline.length > 0 && (
              <section className="activity-section">
                <h2>Recent Activity</h2>
                <div className="recent-timeline">
                  {timeline.slice(0, 5).map((event, index) => (
                    <TimelineEvent key={event.id || index} event={event} />
                  ))}
                </div>
              </section>
            )}

            {/* Contact Your Loan Officer */}
            <ContactLOCard onSchedule={() => setShowScheduleModal(true)} />
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

            <div className="documents-grid">
              {documents.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">📁</div>
                  <p>No documents uploaded yet</p>
                  <p className="empty-hint">Upload documents using the button above</p>
                </div>
              ) : (
                documents.map(doc => (
                  <DocumentCard
                    key={doc.id}
                    document={doc}
                    onDownload={handleDownload}
                  />
                ))
              )}
            </div>
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div className="tab-content tasks-tab">
            <h2>Your Tasks</h2>

            <div className="tasks-section">
              <h3>To Do ({tasks.filter(t => t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS').length})</h3>
              {tasks.filter(t => t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS').map(task => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onComplete={handleTaskComplete}
                />
              ))}
              {tasks.filter(t => t.status === 'open' || t.status === 'TODO' || t.status === 'IN_PROGRESS').length === 0 && (
                <div className="empty-state">
                  <p>No pending tasks - great job!</p>
                </div>
              )}
            </div>

            <div className="tasks-section completed-tasks">
              <h3>Completed ({tasks.filter(t => t.status === 'completed' || t.status === 'DONE').length})</h3>
              {tasks.filter(t => t.status === 'completed' || t.status === 'DONE').slice(0, 5).map(task => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onComplete={handleTaskComplete}
                />
              ))}
            </div>
          </div>
        )}

        {/* Timeline Tab */}
        {activeTab === 'timeline' && (
          <div className="tab-content timeline-tab">
            <h2>Loan Timeline</h2>

            <section className="milestones-section">
              <h3>Milestones</h3>
              <MilestoneTracker milestones={milestones} />
            </section>

            <section className="activity-section">
              <h3>Activity History</h3>
              <div className="timeline-list">
                {timeline.length === 0 ? (
                  <div className="empty-state">
                    <p>No activity yet</p>
                  </div>
                ) : (
                  timeline.map((event, index) => (
                    <TimelineEvent key={event.id || index} event={event} />
                  ))
                )}
              </div>
            </section>
          </div>
        )}

        {/* Messages Tab */}
        {activeTab === 'messages' && (
          <div className="tab-content messages-tab">
            <h2>Messages</h2>

            <form className="message-form" onSubmit={handleSendMessage}>
              <input
                type="text"
                placeholder="Subject (optional)"
                value={newMessage.subject}
                onChange={(e) => setNewMessage({ ...newMessage, subject: e.target.value })}
              />
              <textarea
                placeholder="Write a message to your loan team..."
                value={newMessage.body}
                onChange={(e) => setNewMessage({ ...newMessage, body: e.target.value })}
                rows={3}
              />
              <button type="submit" disabled={sendingMessage || !newMessage.body.trim()}>
                {sendingMessage ? 'Sending...' : 'Send Message'}
              </button>
            </form>

            <div className="messages-list">
              {messages.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">💬</div>
                  <p>No messages yet</p>
                  <p className="empty-hint">Send a message using the form above</p>
                </div>
              ) : (
                messages.map(message => (
                  <MessageItem
                    key={message.id}
                    message={message}
                    isMine={message.direction === 'inbound'}
                  />
                ))
              )}
            </div>
          </div>
        )}

        {/* Calculator Tab */}
        {activeTab === 'calculator' && (
          <div className="tab-content calculator-tab">
            <h2>Payment Calculator</h2>
            <p className="calculator-intro">
              Estimate your monthly payment and explore different scenarios.
            </p>
            <PaymentCalculator
              initialHomeValue={loan?.loan_amount ? Math.round(loan.loan_amount / 0.8) : 400000}
              initialDownPayment={loan?.loan_amount ? Math.round(loan.loan_amount * 0.2 / 0.8) : 80000}
              initialState={loan?.property_address?.state || ''}
              initialCounty={loan?.property_address?.county || ''}
              initialCreditScore={720}
              initialLoanType={loan?.product_type?.toLowerCase().includes('fha') ? 'fha' :
                              loan?.product_type?.toLowerCase().includes('va') ? 'va' :
                              loan?.product_type?.toLowerCase().includes('usda') ? 'usda' : 'conventional'}
              compact={false}
              showAdvancedOptions={true}
            />
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
