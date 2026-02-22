/**
 * PURL Borrower Portal
 *
 * Main portal page for borrowers to access their workspace through
 * a persistent URL. Provides access to:
 * - Loan status and terms
 * - Document needs list and uploads
 * - Task management
 * - Timeline/milestones
 * - Appointment scheduling
 * - Payment calculators
 * - Messages with loan team
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  api,
  useWorkspaceData,
  useWorkspaceMilestones,
  useDocumentUpload,
  useSendMessage,
} from '../lib/api';
import ScheduleAppointmentModal from '../components/ScheduleAppointmentModal';
import PaymentCalculator from '../components/PaymentCalculator';
import PortalDocumentRequirements from '../components/Portal/PortalDocumentRequirements';
import PortalOnboardingGuide from '../components/Portal/PortalOnboardingGuide';
import './PURLPortal.css';

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

// Document card component
const DocumentCard = ({ document, onDownload }) => {
  const statusIcons = {
    pending: '⏳',
    uploaded: '⏳',
    scanning: '🔍',
    processing: '⚙️',
    approved: '✓',
    rejected: '✗',
    deleted: '🗑️',
    expired: '⏱️',
    error: '⚠️'
  };

  // Normalize status to lowercase for comparison
  const statusLower = (document.status || 'pending').toLowerCase();
  const displayIcon = statusIcons[statusLower] || '⏳';

  return (
    <div className={`document-card status-${statusLower}`}>
      <div className="doc-icon">📄</div>
      <div className="doc-info">
        <div className="doc-name">{document.filename}</div>
        <div className="doc-meta">
          {document.document_type && <span>{document.document_type}</span>}
          <span>{new Date(document.uploaded_at).toLocaleDateString()}</span>
        </div>
      </div>
      <div className="doc-status">
        <span className="status-icon">{displayIcon}</span>
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

// Application field labels for Q&A display
const APPLICATION_FIELD_LABELS = {
  // Personal Information
  borrower_first_name: 'First Name',
  borrower_last_name: 'Last Name',
  borrower_email: 'Email Address',
  borrower_phone: 'Phone Number',
  borrower_dob: 'Date of Birth',
  ssn_last4: 'Last 4 of SSN',

  // Employment & Income
  employment_status: 'Employment Status',
  employer_name: 'Employer Name',
  job_title: 'Job Title',
  years_employed: 'Years at Job',
  annual_income: 'Annual Income',
  monthly_income: 'Monthly Income',

  // Loan Details
  loan_purpose: 'Loan Purpose',
  loan_type: 'Loan Type',
  loan_amount: 'Loan Amount',
  down_payment: 'Down Payment',
  down_payment_percent: 'Down Payment %',
  loan_term: 'Loan Term',
  interest_rate: 'Interest Rate',

  // Property Information
  property_type: 'Property Type',
  property_address: 'Street Address',
  property_city: 'City',
  property_state: 'State',
  property_zip: 'ZIP Code',
  occupancy_type: 'Occupancy Type',
  estimated_value: 'Estimated Property Value',
  purchase_price: 'Purchase Price',

  // Credit & Assets
  credit_score_range: 'Credit Score Range',
  estimated_credit_score: 'Estimated Credit Score',
  has_bankruptcy: 'Bankruptcy History',
  has_foreclosure: 'Foreclosure History',
  total_assets: 'Total Assets',
  total_monthly_debt: 'Total Monthly Debt',

  // Co-Borrower
  has_co_borrower: 'Has Co-Borrower',
  co_borrower_first_name: 'Co-Borrower First Name',
  co_borrower_last_name: 'Co-Borrower Last Name',
  co_borrower_email: 'Co-Borrower Email',
  co_borrower_phone: 'Co-Borrower Phone',

  // Additional Info
  referral_source: 'How Did You Hear About Us',
  preferred_contact_method: 'Preferred Contact Method',
  preferred_contact_time: 'Best Time to Contact',
  notes: 'Additional Notes',

  // Consent
  credit_auth_consent: 'Credit Authorization',
  econsent: 'Electronic Consent',
};

// Value formatter for display
const formatApplicationValue = (key, value) => {
  if (value === null || value === undefined || value === '') return '—';

  // Boolean values
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (value === 'true') return 'Yes';
  if (value === 'false') return 'No';

  // Currency fields
  if (['loan_amount', 'down_payment', 'annual_income', 'monthly_income',
       'estimated_value', 'purchase_price', 'total_assets', 'total_monthly_debt'].includes(key)) {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(num);
    }
  }

  // Percentage fields
  if (key === 'down_payment_percent' || key === 'interest_rate') {
    const num = parseFloat(value);
    if (!isNaN(num)) return `${num}%`;
  }

  // Loan term
  if (key === 'loan_term') {
    return `${value} Years`;
  }

  // Date fields
  if (key === 'borrower_dob') {
    try {
      return new Date(value).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return value;
    }
  }

  // Employment status
  if (key === 'employment_status') {
    const statusMap = {
      employed: 'Employed',
      self_employed: 'Self-Employed',
      retired: 'Retired',
      not_employed: 'Not Employed',
    };
    return statusMap[value] || value;
  }

  // Loan purpose
  if (key === 'loan_purpose') {
    const purposeMap = {
      purchase: 'Purchase a Home',
      refinance: 'Refinance',
      cash_out: 'Cash-Out Refinance',
      construction: 'Construction Loan',
    };
    return purposeMap[value] || value;
  }

  // Property type
  if (key === 'property_type') {
    const typeMap = {
      single_family: 'Single Family Home',
      condo: 'Condominium',
      townhouse: 'Townhouse',
      multi_family: 'Multi-Family (2-4 units)',
      manufactured: 'Manufactured Home',
    };
    return typeMap[value] || value;
  }

  // Occupancy type
  if (key === 'occupancy_type') {
    const occMap = {
      primary: 'Primary Residence',
      PRIMARY: 'Primary Residence',
      second_home: 'Second Home',
      SECOND_HOME: 'Second Home',
      investment: 'Investment Property',
      INVESTMENT: 'Investment Property',
    };
    return occMap[value] || value;
  }

  return value;
};

// Application Details Component - Shows all Q&A from application
const ApplicationDetails = ({ application, workspace }) => {
  if (!application || !application.data || Object.keys(application.data).length === 0) {
    return (
      <div className="application-empty-state">
        <div className="empty-icon">📝</div>
        <h3>No Application Data</h3>
        <p>Your application details will appear here once you start your application.</p>
      </div>
    );
  }

  const data = application.data;

  // Group fields by section
  const sections = [
    {
      title: 'Personal Information',
      fields: ['borrower_first_name', 'borrower_last_name', 'borrower_email',
               'borrower_phone', 'borrower_dob', 'ssn_last4']
    },
    {
      title: 'Employment & Income',
      fields: ['employment_status', 'employer_name', 'job_title',
               'years_employed', 'annual_income', 'monthly_income']
    },
    {
      title: 'Loan Details',
      fields: ['loan_purpose', 'loan_type', 'loan_amount', 'down_payment',
               'down_payment_percent', 'loan_term', 'interest_rate']
    },
    {
      title: 'Property Information',
      fields: ['property_type', 'property_address', 'property_city',
               'property_state', 'property_zip', 'occupancy_type',
               'estimated_value', 'purchase_price']
    },
    {
      title: 'Credit & Financial',
      fields: ['credit_score_range', 'estimated_credit_score', 'has_bankruptcy',
               'has_foreclosure', 'total_assets', 'total_monthly_debt']
    },
    {
      title: 'Co-Borrower Information',
      fields: ['has_co_borrower', 'co_borrower_first_name', 'co_borrower_last_name',
               'co_borrower_email', 'co_borrower_phone']
    },
    {
      title: 'Additional Information',
      fields: ['referral_source', 'preferred_contact_method', 'preferred_contact_time', 'notes']
    }
  ];

  // Also include any fields not in our defined sections
  const definedFields = new Set(sections.flatMap(s => s.fields));
  const extraFields = Object.keys(data).filter(key =>
    !definedFields.has(key) &&
    !['id', 'created_at', 'updated_at', 'workspace_id', 'organization_id',
      'credit_auth_consent', 'econsent', 'credit_auth_timestamp', 'econsent_timestamp'].includes(key)
  );

  if (extraFields.length > 0) {
    sections.push({
      title: 'Other Information',
      fields: extraFields
    });
  }

  return (
    <div className="application-details">
      <div className="application-header">
        <div className="application-status">
          <span className="status-label">Status:</span>
          <span className={`status-value status-${application.status || 'in_progress'}`}>
            {(application.status || 'in_progress').replace('_', ' ').toUpperCase()}
          </span>
        </div>
        {application.submitted_at && (
          <div className="submitted-info">
            Submitted: {new Date(application.submitted_at).toLocaleDateString('en-US', {
              month: 'long',
              day: 'numeric',
              year: 'numeric',
              hour: 'numeric',
              minute: '2-digit'
            })}
          </div>
        )}
        {application.completeness_pct !== undefined && (
          <div className="completeness-info">
            Completeness: {application.completeness_pct}%
          </div>
        )}
      </div>

      {sections.map((section, sectionIndex) => {
        // Filter to only fields that have values in the data
        const filledFields = section.fields.filter(field =>
          data[field] !== null && data[field] !== undefined && data[field] !== ''
        );

        // Skip sections with no filled fields
        if (filledFields.length === 0) return null;

        return (
          <div key={sectionIndex} className="application-section">
            <h3 className="section-title">{section.title}</h3>
            <div className="qa-list">
              {filledFields.map(field => (
                <div key={field} className="qa-item">
                  <div className="qa-question">
                    {APPLICATION_FIELD_LABELS[field] || field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </div>
                  <div className="qa-answer">
                    {formatApplicationValue(field, data[field])}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Consent confirmations */}
      {(data.credit_auth_consent || data.econsent) && (
        <div className="application-section consents-section">
          <h3 className="section-title">Authorizations & Consents</h3>
          <div className="qa-list">
            {data.credit_auth_consent && (
              <div className="qa-item consent-item">
                <div className="qa-question">Credit Authorization</div>
                <div className="qa-answer consent-confirmed">
                  ✓ Authorized
                  {data.credit_auth_timestamp && (
                    <span className="consent-date">
                      on {new Date(data.credit_auth_timestamp).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            )}
            {data.econsent && (
              <div className="qa-item consent-item">
                <div className="qa-question">Electronic Consent</div>
                <div className="qa-answer consent-confirmed">
                  ✓ Consented
                  {data.econsent_timestamp && (
                    <span className="consent-date">
                      on {new Date(data.econsent_timestamp).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Loan Summary Card Component - Shows loan details at a glance
const LoanSummaryCard = ({ loan, workspace, contacts }) => {
  const borrower = contacts?.find(c => c.contact_type === 'borrower') || contacts?.[0];
  const daysLeft = daysUntilClose(loan?.target_close_date);

  return (
    <div className="loan-summary-card">
      <div className="loan-header">
        <div className="loan-type-badge">
          {loan?.product_type || loan?.loan_purpose || 'Your Loan'}
        </div>
        <StatusBadge status={workspace?.status} />
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

// Needs List Card - Shows conditions/tasks from loan application submission
const NeedsListCard = ({ tasks, onViewAll, onUpload, showUploadButtons = false }) => {
  const [uploadingId, setUploadingId] = useState(null);

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

  const handleFileSelect = async (task, event) => {
    const file = event.target.files?.[0];
    if (!file || !onUpload) return;

    setUploadingId(task.id);
    try {
      await onUpload(task, file);
    } finally {
      setUploadingId(null);
    }
  };

  // If no tasks, show empty state
  if (!tasks || tasks.length === 0) {
    return (
      <div className="document-checklist-card">
        <div className="checklist-header">
          <h3>Documents Needed</h3>
        </div>
        <div className="checklist-empty">
          <p>Your document checklist will appear here once your application is processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="document-checklist-card">
      <div className="checklist-header">
        <h3>Documents Needed</h3>
        <span className="completion-badge">{completionPct}% Complete</span>
      </div>

      <ProgressBar percentage={completionPct} label="Documents" />

      <div className="checklist-items">
        {/* Show pending tasks/documents */}
        {pendingTasks.map((task) => {
          const displayStatus = getDisplayStatus(task.status);
          const isUploading = uploadingId === task.id;
          return (
            <div key={task.id} className={`checklist-item status-${displayStatus}`}>
              <span className="checklist-icon">{statusIcons[displayStatus]}</span>
              <div className="checklist-info">
                <span className="checklist-label">{task.title}</span>
                {task.due_at && (
                  <span className="checklist-due">Due: {new Date(task.due_at).toLocaleDateString()}</span>
                )}
              </div>
              {showUploadButtons && onUpload && displayStatus === 'needed' ? (
                <label className="checklist-upload-btn">
                  <input
                    type="file"
                    onChange={(e) => handleFileSelect(task, e)}
                    disabled={isUploading}
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                    style={{ display: 'none' }}
                  />
                  {isUploading ? 'Uploading...' : 'Choose File'}
                </label>
              ) : (
                <span className={`checklist-status status-${displayStatus}`}>{statusLabels[displayStatus]}</span>
              )}
            </div>
          );
        })}

        {/* Show completed tasks */}
        {completedTasks.map((task) => (
          <div key={task.id} className="checklist-item status-done">
            <span className="checklist-icon">{statusIcons.done}</span>
            <span className="checklist-label">{task.title}</span>
            <span className="checklist-status status-done">{statusLabels.done}</span>
          </div>
        ))}
      </div>

      {pendingTasks.length > 10 && onViewAll && (
        <button className="upload-cta-btn" onClick={onViewAll}>
          View All {pendingTasks.length} Items
        </button>
      )}
    </div>
  );
};

// Quick Actions Bar - Provides quick access to common actions
const QuickActionsBar = ({ onSchedule, onMessage, onUpload, onCalculator }) => (
  <div className="quick-actions-bar">
    <button className="quick-action-btn" onClick={onSchedule}>
      <span className="action-icon">📅</span>
      <span className="action-label">Schedule Call</span>
    </button>
    <button className="quick-action-btn" onClick={onMessage}>
      <span className="action-icon">💬</span>
      <span className="action-label">Message</span>
    </button>
    <button className="quick-action-btn" onClick={onUpload}>
      <span className="action-icon">📄</span>
      <span className="action-label">Upload Docs</span>
    </button>
    <button className="quick-action-btn" onClick={onCalculator}>
      <span className="action-icon">🧮</span>
      <span className="action-label">Calculator</span>
    </button>
  </div>
);

// Main portal component
export default function PURLPortal() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Get token from URL or localStorage - initialize synchronously
  const getToken = () => {
    const urlParams = new URLSearchParams(location.search);
    const urlToken = urlParams.get('token');
    if (urlToken) {
      localStorage.setItem(`purl_token_${slug}`, urlToken);
      return urlToken;
    }
    return localStorage.getItem(`purl_token_${slug}`);
  };

  const [token] = useState(getToken);
  const [tokenReady, setTokenReady] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Set API token on mount and when token changes - BEFORE data fetching
  React.useEffect(() => {
    if (token) {
      api.setAuthToken(token);
      // Small delay to ensure token is set before fetch
      setTokenReady(true);
    }
  }, [token, slug]);

  // Check for submission success message
  const urlParams = new URLSearchParams(location.search);
  const justSubmitted = urlParams.get('submitted') === 'true';
  const [showSubmitSuccess, setShowSubmitSuccess] = useState(justSubmitted);

  // Onboarding guide - show for first-time visitors or after submission
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Use workspace data hook - only enabled after token is ready
  const {
    data: workspaceData,
    loading,
    error,
    refetch: refetchWorkspace,
  } = useWorkspaceData(tokenReady ? slug : null); // Pass null slug to disable until token ready

  // Check if should show onboarding (after data loads)
  useEffect(() => {
    console.log('[PURLPortal] Onboarding check:', {
      hasWorkspaceData: !!workspaceData,
      loading,
      slug,
      justSubmitted
    });
    if (workspaceData && !loading) {
      const storageKey = `portal_onboarding_${slug}`;
      const hasSeenGuide = localStorage.getItem(storageKey);
      console.log('[PURLPortal] Onboarding storage check:', { storageKey, hasSeenGuide });
      // Show onboarding for first-time visitors or if just submitted
      if (!hasSeenGuide || justSubmitted) {
        // Small delay to let the UI render
        console.log('[PURLPortal] Starting onboarding timer...');
        const timer = setTimeout(() => {
          console.log('[PURLPortal] Setting showOnboarding to true');
          setShowOnboarding(true);
        }, 800);
        return () => clearTimeout(timer);
      }
    }
  }, [workspaceData, loading, slug, justSubmitted]);

  // Restart the portal tour
  const restartTour = () => {
    const storageKey = `portal_onboarding_${slug}`;
    localStorage.removeItem(storageKey);
    setShowOnboarding(true);
  };

  // Debug logging for workspace data fetch
  React.useEffect(() => {
    if (error) {
      console.error('[PURLPortal] Error loading workspace:', error);
    }
    if (workspaceData) {
      console.log('[PURLPortal] Workspace data loaded:', workspaceData?.workspace?.id);
    }
    console.log('[PURLPortal] State:', { tokenReady, loading, hasError: !!error, hasData: !!workspaceData });
  }, [tokenReady, loading, error, workspaceData]);

  // Extract data from workspace response
  const workspace = workspaceData?.workspace;
  const application = workspaceData?.application;
  const loan = workspaceData?.loan;
  const contacts = workspaceData?.contacts || [];
  const borrower = contacts.find(c => c.contact_type === 'borrower') || contacts[0];
  const [documents, setDocuments] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [messages, setMessages] = useState([]);
  const [modules, setModules] = useState([]);
  const [uploading, setUploading] = useState(false);

  // Message form state
  const [newMessage, setNewMessage] = useState({ subject: '', body: '' });

  // Use send message hook
  const { mutate: sendMessageMutation, loading: sendingMessage } = useSendMessage(slug);

  // Sync workspace data when it changes
  useEffect(() => {
    if (workspaceData) {
      setDocuments(workspaceData.documents || []);
      setTasks(workspaceData.tasks || []);
      setMilestones(workspaceData.milestones || []);
      setTimeline(workspaceData.timeline || []);
      setModules(workspaceData.modules || []);
    }
  }, [workspaceData]);

  // Load messages
  const loadMessages = useCallback(async () => {
    try {
      const data = await api.getWorkspaceMessages(slug);
      setMessages(data.messages || []);
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
      const data = await api.getDocumentDownload(documentId, workspace?.id);
      window.open(data.download_url, '_blank');
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

  // Handle document upload for specific task/document need
  const handleTaskDocumentUpload = async (task, file) => {
    if (!file) return;

    try {
      // Upload document for this specific task
      try {
        const uploadData = await api.getDocumentUploadUrl(slug, {
          filename: file.name,
          contentType: file.type,
          doc_type: task.title, // Associate with the task/document type
          task_id: task.id,
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
          throw new Error(`Upload failed: ${s3Response.status}`);
        }

        // Complete upload
        await api.completeDocumentUpload(slug, {
          documentKey: uploadData.document_key,
          filename: file.name,
          fileSize: file.size,
          contentType: file.type,
          task_id: task.id,
        });
      } catch (s3Error) {
        console.warn('S3 upload failed, trying direct upload:', s3Error);
        await api.uploadDocumentDirect(slug, file, { task_id: task.id });
      }

      // Mark task as in progress after upload
      await api.updateTask(slug, task.id, {
        status: 'IN_PROGRESS',
      });

      // Refresh tasks and documents
      const tasksData = await api.getWorkspaceTasks(slug);
      setTasks(tasksData.tasks || []);

      const docsData = await api.getWorkspaceDocuments(slug);
      setDocuments(docsData.documents || []);

      toast.success(`${task.title} uploaded successfully! It will be reviewed shortly.`);
    } catch (err) {
      console.error('Task document upload failed:', err);
      toast.error(`Failed to upload ${file.name}: ${err.message || 'Unknown error'}`);
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

    try {
      await sendMessageMutation({
        content: newMessage.body,
        messageType: 'text',
      });
      setNewMessage({ subject: '', body: '' });
      loadMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
      toast.error('Failed to send message');
    }
  };

  // No token - show access error
  if (!token) {
    return (
      <div className="purl-portal error">
        <div className="error-container">
          <div className="error-icon">🔐</div>
          <h2>Access Required</h2>
          <p>Please use your portal access link to view this page.</p>
          <p className="error-help">
            Contact your loan officer for a new portal link.
          </p>
        </div>
      </div>
    );
  }

  // Loading state - show while token is initializing OR data is loading
  if (!tokenReady || loading) {
    return (
      <div className="purl-portal loading">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading your portal...</p>
          {!tokenReady && <p className="loading-detail">Authenticating...</p>}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    const isAuthError = error?.status === 401;
    return (
      <div className="purl-portal error">
        <div className="error-container">
          <div className="error-icon">⚠️</div>
          <h2>{isAuthError ? 'Session Expired' : 'Access Error'}</h2>
          <p>{isAuthError ? 'Your session has expired. Please use your portal link again.' : error?.message || 'An error occurred'}</p>
          <p className="error-help">
            Please contact your loan officer for a new portal link.
          </p>
        </div>
      </div>
    );
  }

  // Calculate counts for badges
  const pendingTasksCount = tasks.filter(t => t.status === 'open').length;
  const unreadMessagesCount = messages.filter(m => !m.is_read && m.direction === 'outbound').length;

  return (
    <div className="purl-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="header-content">
          <div className="workspace-info">
            <h1>{workspace?.display_name || 'Your Loan Portal'}</h1>
            <StatusBadge status={workspace?.status} />
          </div>
          <div className="header-actions">
            {application && (
              <ProgressBar
                percentage={application.completeness_pct || 0}
                label="Application Progress"
              />
            )}
            <button
              className="tour-btn"
              onClick={restartTour}
              title="Take a tour of the portal"
            >
              <span className="tour-icon">?</span>
              <span className="tour-label">Tour</span>
            </button>
          </div>
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
          label="Application"
          icon="📝"
          isActive={activeTab === 'application'}
          onClick={() => setActiveTab('application')}
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
            <LoanSummaryCard loan={loan} workspace={workspace} contacts={contacts} />

            {/* Quick Actions Bar */}
            <QuickActionsBar
              onSchedule={() => setShowScheduleModal(true)}
              onMessage={() => setActiveTab('messages')}
              onUpload={() => setActiveTab('documents')}
              onCalculator={() => setActiveTab('calculator')}
            />

            {/* Two Column Layout */}
            <div className="overview-columns">
              {/* Left Column - Needs List (Conditions from application) */}
              <div className="overview-column">
                <NeedsListCard
                  tasks={tasks}
                  onViewAll={() => setActiveTab('tasks')}
                />
              </div>

              {/* Right Column - Progress & Tasks */}
              <div className="overview-column">
                <section className="overview-section">
                  <h2>Loan Progress</h2>
                  <MilestoneTracker milestones={milestones} />
                </section>

                <section className="overview-section">
                  <h2>Your To-Do List</h2>
                  {tasks.filter(t => t.status === 'open').length === 0 ? (
                    <div className="empty-state">
                      <p>✓ No pending tasks - you're all caught up!</p>
                    </div>
                  ) : (
                    <>
                      {tasks.filter(t => t.status === 'open').slice(0, 3).map(task => (
                        <TaskCard
                          key={task.id}
                          task={task}
                          onComplete={handleTaskComplete}
                        />
                      ))}
                      {pendingTasksCount > 3 && (
                        <button
                          className="view-all-btn"
                          onClick={() => setActiveTab('tasks')}
                        >
                          View all {pendingTasksCount} tasks →
                        </button>
                      )}
                    </>
                  )}
                </section>

                <section className="overview-section">
                  <h2>Recent Activity</h2>
                  <div className="recent-timeline">
                    {timeline.length === 0 ? (
                      <div className="empty-state">
                        <p>Activity will appear here as your loan progresses.</p>
                      </div>
                    ) : (
                      timeline.slice(0, 5).map((event, index) => (
                        <TimelineEvent key={event.id || index} event={event} />
                      ))
                    )}
                  </div>
                </section>
              </div>
            </div>
          </div>
        )}

        {/* Application Tab */}
        {activeTab === 'application' && (
          <div className="tab-content application-tab">
            <h2>Your Application</h2>
            <p className="tab-intro">
              Review all the information you provided in your loan application.
            </p>
            <ApplicationDetails application={application} workspace={workspace} />
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="tab-content documents-tab">
            {/* Document Needs List - Primary upload interface with file upload buttons */}
            <NeedsListCard
              tasks={tasks}
              onViewAll={() => setActiveTab('tasks')}
              onUpload={handleTaskDocumentUpload}
              showUploadButtons={true}
            />

            {/* Smart Docs Requirements (additional requirements from SmartDocs system) */}
            <PortalDocumentRequirements
              workspaceSlug={slug}
              onProgressUpdate={(progress) => {
                // Could update a progress indicator if needed
                console.log('Document progress:', progress);
              }}
            />

            {/* Additional Uploaded Documents */}
            {documents.length > 0 && (
              <div className="additional-documents">
                <h3>Additional Uploads</h3>
                <div className="documents-header">
                  <label className="upload-btn">
                    <input
                      type="file"
                      multiple
                      onChange={handleUpload}
                      disabled={uploading}
                      accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                    />
                    {uploading ? 'Uploading...' : '+ Upload Other Document'}
                  </label>
                </div>
                <div className="documents-grid">
                  {documents.map(doc => (
                    <DocumentCard
                      key={doc.id}
                      document={doc}
                      onDownload={handleDownload}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div className="tab-content tasks-tab">
            <h2>Your Tasks</h2>

            <div className="tasks-section">
              <h3>To Do ({tasks.filter(t => t.status === 'open').length})</h3>
              {tasks.filter(t => t.status === 'open').map(task => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onComplete={handleTaskComplete}
                />
              ))}
              {tasks.filter(t => t.status === 'open').length === 0 && (
                <div className="empty-state">
                  <p>No pending tasks - great job!</p>
                </div>
              )}
            </div>

            <div className="tasks-section completed-tasks">
              <h3>Completed ({tasks.filter(t => t.status === 'completed').length})</h3>
              {tasks.filter(t => t.status === 'completed').slice(0, 5).map(task => (
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

      {/* Onboarding Guide for first-time visitors */}
      {console.log('[PURLPortal] Render - showOnboarding:', showOnboarding)}
      {showOnboarding && (
        <PortalOnboardingGuide
          workspaceSlug={slug}
          onComplete={() => setShowOnboarding(false)}
          forceShow={justSubmitted}
        />
      )}
    </div>
  );
}
