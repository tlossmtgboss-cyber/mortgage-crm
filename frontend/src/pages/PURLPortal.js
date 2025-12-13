/**
 * PURL Borrower Portal
 *
 * Main portal page for borrowers to access their workspace through
 * a persistent URL. Provides access to:
 * - Application status and progress
 * - Document uploads
 * - Task management
 * - Timeline/milestones
 * - Messages with loan team
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  api,
  useWorkspaceData,
  useWorkspaceMilestones,
  useDocumentUpload,
  useSendMessage,
} from '../lib/api';
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

// Main portal component
export default function PURLPortal() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Get token from URL or localStorage
  const getToken = () => {
    const urlParams = new URLSearchParams(location.search);
    const urlToken = urlParams.get('token');
    if (urlToken) {
      localStorage.setItem(`purl_token_${slug}`, urlToken);
      // Set auth token on API client
      api.setAuthToken(urlToken);
      return urlToken;
    }
    const storedToken = localStorage.getItem(`purl_token_${slug}`);
    if (storedToken) {
      api.setAuthToken(storedToken);
    }
    return storedToken;
  };

  const [token] = useState(getToken);
  const [activeTab, setActiveTab] = useState('overview');

  // Use workspace data hook
  const {
    data: workspaceData,
    loading,
    error,
    refetch: refetchWorkspace,
  } = useWorkspaceData(slug);

  // Extract data from workspace response
  const workspace = workspaceData?.workspace;
  const application = workspaceData?.application;
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

    try {
      await sendMessageMutation({
        content: newMessage.body,
        messageType: 'text',
      });
      setNewMessage({ subject: '', body: '' });
      loadMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
      alert('Failed to send message');
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

  // Loading state
  if (loading) {
    return (
      <div className="purl-portal loading">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading your portal...</p>
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
          {application && (
            <ProgressBar
              percentage={application.completeness_pct || 0}
              label="Application Progress"
            />
          )}
        </div>
      </header>

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
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="tab-content overview-tab">
            <section className="overview-section">
              <h2>Loan Progress</h2>
              <MilestoneTracker milestones={milestones} />
            </section>

            <section className="overview-section">
              <h2>Your To-Do List</h2>
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
            </section>

            <section className="overview-section">
              <h2>Recent Activity</h2>
              <div className="recent-timeline">
                {timeline.slice(0, 5).map((event, index) => (
                  <TimelineEvent key={event.id || index} event={event} />
                ))}
              </div>
            </section>
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
      </main>

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
