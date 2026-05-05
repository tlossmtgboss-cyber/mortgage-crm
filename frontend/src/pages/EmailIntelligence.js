import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import './EmailIntelligence.css';
import { toast } from '../utils/toast';

function EmailIntelligence() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('queue'); // 'queue', 'conversations', 'documents', 'sla'
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState(null);

  // Queue state
  const [emailQueue, setEmailQueue] = useState([]);
  const [queueTotal, setQueueTotal] = useState(0);
  const [queueFilters, setQueueFilters] = useState({
    status: 'pending',
    disposition: '',
    hasMatch: ''
  });

  // Conversation log state
  const [conversations, setConversations] = useState([]);
  const [conversationTotal, setConversationTotal] = useState(0);
  const [selectedLoanId, setSelectedLoanId] = useState('');

  // Document tracking state
  const [documents, setDocuments] = useState([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [docLoanId, setDocLoanId] = useState('');

  // SLA tracking state
  const [slaItems, setSlaItems] = useState([]);
  const [slaTotal, setSlaTotal] = useState(0);

  // All documents state (global view)
  const [allDocuments, setAllDocuments] = useState([]);
  const [allDocumentsTotal, setAllDocumentsTotal] = useState(0);

  // Stats
  const [stats, setStats] = useState({});

  // Selected email for detail view
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Disposition dialog
  const [showDispositionDialog, setShowDispositionDialog] = useState(false);
  const [dispositionEmail, setDispositionEmail] = useState(null);
  const [selectedDisposition, setSelectedDisposition] = useState('');
  const [createTask, setCreateTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');

  const dispositionOptions = [
    { value: 'document_received', label: 'Document Received', icon: '📄' },
    { value: 'document_request', label: 'Document Request', icon: '📋' },
    { value: 'action_required', label: 'Action Required', icon: '⚡' },
    { value: 'general_correspondence', label: 'General Correspondence', icon: '💬' },
    { value: 'status_update', label: 'Status Update', icon: '📊' },
    { value: 'rate_lock_request', label: 'Rate Lock Request', icon: '🔒' },
    { value: 'closing_related', label: 'Closing Related', icon: '🏠' },
    { value: 'skip', label: 'Skip/Archive', icon: '⏭️' }
  ];

  // Load data based on active tab
  useEffect(() => {
    loadData();
    loadStats();
  }, [activeTab, queueFilters, selectedLoanId, docLoanId]);

  const loadData = async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case 'queue':
          await loadEmailQueue();
          break;
        case 'conversations':
          await loadConversations();
          break;
        case 'documents':
          await loadDocuments();
          break;
        case 'all-documents':
          await loadAllDocuments();
          break;
        case 'sla':
          await loadSlaItems();
          break;
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await api.get('/api/v1/email-intelligence/stats');
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const loadEmailQueue = async () => {
    try {
      const params = { limit: 50 };
      if (queueFilters.status) params.status = queueFilters.status;
      if (queueFilters.disposition) params.disposition = queueFilters.disposition;
      if (queueFilters.hasMatch === 'yes') params.has_match = true;
      if (queueFilters.hasMatch === 'no') params.has_match = false;

      const response = await api.get('/api/v1/email-intelligence/queue', { params });
      setEmailQueue(response.data.emails || []);
      setQueueTotal(response.data.total || 0);
    } catch (error) {
      console.error('Error loading email queue:', error);
    }
  };

  const loadConversations = async () => {
    if (!selectedLoanId) {
      setConversations([]);
      setConversationTotal(0);
      return;
    }
    try {
      const response = await api.get(
        `/api/v1/email-intelligence/conversation-log/loan/${selectedLoanId}`,
        { params: { limit: 50 } }
      );
      setConversations(response.data.entries || []);
      setConversationTotal(response.data.total || 0);
    } catch (error) {
      console.error('Error loading conversations:', error);
    }
  };

  const loadDocuments = async () => {
    if (!docLoanId) {
      setDocuments([]);
      setDocumentTotal(0);
      return;
    }
    try {
      const response = await api.get(
        `/api/v1/email-intelligence/document-tracking/loan/${docLoanId}`
      );
      setDocuments(response.data.documents || []);
      setDocumentTotal(response.data.total || 0);
    } catch (error) {
      console.error('Error loading documents:', error);
    }
  };

  const loadSlaItems = async () => {
    try {
      const response = await api.get('/api/v1/email-intelligence/sla-tracking');
      setSlaItems(response.data.slas || []);
      setSlaTotal(response.data.total || 0);
    } catch (error) {
      console.error('Error loading SLA items:', error);
    }
  };

  const loadAllDocuments = async () => {
    try {
      const response = await api.get(
        '/api/v1/email-intelligence/document-tracking/all',
        { params: { limit: 100 } }
      );
      setAllDocuments(response.data.documents || []);
      setAllDocumentsTotal(response.data.total || 0);
    } catch (error) {
      console.error('Error loading all documents:', error);
    }
  };

  const handleViewEmail = (email) => {
    setSelectedEmail(email);
    setShowDetailModal(true);
  };

  const handleOpenDisposition = (email) => {
    setDispositionEmail(email);
    setSelectedDisposition(email.ai_analysis?.disposition || 'general_correspondence');
    setCreateTask(false);
    setTaskTitle(`Follow up: ${email.subject || 'Email'}`);
    setShowDispositionDialog(true);
  };

  const handleProcessEmail = async () => {
    if (!dispositionEmail || !selectedDisposition) return;

    setProcessingId(dispositionEmail.id);
    try {
      const params = { disposition: selectedDisposition };
      if (createTask) {
        params.create_task = true;
        params.task_title = taskTitle;
      }

      const response = await api.post(
        `/api/v1/email-intelligence/queue/${dispositionEmail.id}/process-with-intelligence`,
        null,
        { params }
      );
      console.log('Process result:', response.data);
      setShowDispositionDialog(false);
      setDispositionEmail(null);
      loadData();
      loadStats();
    } catch (error) {
      console.error('Error processing email:', error);
      const detail = error.response?.data?.detail || error.response?.data?.error || 'Failed to process email';
      toast.error(`Error: ${detail}`);
    } finally {
      setProcessingId(null);
    }
  };

  const handleMarkSlaResponded = async (slaId) => {
    try {
      await api.post(`/api/v1/email-intelligence/sla-tracking/${slaId}/respond`);
      loadSlaItems();
      loadStats();
    } catch (error) {
      console.error('Error marking SLA responded:', error);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'positive': return '#4caf50';
      case 'negative': return '#f44336';
      case 'urgent': return '#ff9800';
      default: return '#9e9e9e';
    }
  };

  const getUrgencyLabel = (level) => {
    if (level >= 5) return { label: 'Critical', color: '#f44336' };
    if (level >= 4) return { label: 'Urgent', color: '#ff9800' };
    if (level >= 3) return { label: 'Normal', color: '#2196f3' };
    return { label: 'Low', color: '#9e9e9e' };
  };

  return (
    <div className="email-intelligence-page">
      <div className="page-header">
        <h1>Email Intelligence</h1>
        <p className="subtitle">AI-powered email analysis, conversation tracking, and document management</p>
      </div>

      {/* Stats Summary - Clickable cards */}
      <div className="stats-grid">
        <div
          className="stat-card clickable"
          onClick={() => {
            setQueueFilters({ ...queueFilters, status: 'pending' });
            setActiveTab('queue');
          }}
          title="Click to view pending emails"
        >
          <div className="stat-value">{stats.pending_count || 0}</div>
          <div className="stat-label">Pending Emails</div>
        </div>
        <div
          className="stat-card clickable"
          onClick={() => {
            setQueueFilters({ ...queueFilters, status: 'processed' });
            setActiveTab('queue');
          }}
          title="Click to view processed emails"
        >
          <div className="stat-value">{stats.processed_count || 0}</div>
          <div className="stat-label">Processed</div>
        </div>
        <div
          className="stat-card clickable"
          onClick={() => setActiveTab('conversations')}
          title="Click to view conversation logs"
        >
          <div className="stat-value">{stats.conversation_logs_created || 0}</div>
          <div className="stat-label">Conversations</div>
        </div>
        <div
          className="stat-card clickable"
          onClick={() => setActiveTab('all-documents')}
          title="Click to view all received documents"
        >
          <div className="stat-value">{stats.documents_received || 0}</div>
          <div className="stat-label">Docs Received</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs-container">
        <button
          className={`tab-button ${activeTab === 'queue' ? 'active' : ''}`}
          onClick={() => setActiveTab('queue')}
        >
          Email Queue ({stats.pending_count || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'conversations' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversations')}
        >
          Conversation Logs
        </button>
        <button
          className={`tab-button ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Document Tracking
        </button>
        <button
          className={`tab-button ${activeTab === 'sla' ? 'active' : ''}`}
          onClick={() => setActiveTab('sla')}
        >
          SLA Tracking
        </button>
        <button
          className={`tab-button ${activeTab === 'all-documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('all-documents')}
        >
          All Documents ({stats.documents_received || 0})
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Email Queue Tab */}
        {activeTab === 'queue' && (
          <div className="queue-section">
            <div className="filters-row">
              <select
                value={queueFilters.status}
                onChange={(e) => setQueueFilters({ ...queueFilters, status: e.target.value })}
              >
                <option value="">All Status</option>
                <option value="pending">Pending</option>
                <option value="processed">Processed</option>
              </select>
              <select
                value={queueFilters.disposition}
                onChange={(e) => setQueueFilters({ ...queueFilters, disposition: e.target.value })}
              >
                <option value="">All Dispositions</option>
                {dispositionOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <select
                value={queueFilters.hasMatch}
                onChange={(e) => setQueueFilters({ ...queueFilters, hasMatch: e.target.value })}
              >
                <option value="">Match Status</option>
                <option value="yes">Has Match</option>
                <option value="no">No Match</option>
              </select>
              <button className="refresh-btn" onClick={loadData}>
                🔄 Refresh
              </button>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : emailQueue.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📭</div>
                <h3>No emails in queue</h3>
                <p>Sync your email to import messages for processing</p>
              </div>
            ) : (
              <div className="email-list">
                {emailQueue.map(email => (
                  <div key={email.id} className={`email-card ${email.status}`}>
                    <div className="email-header">
                      <div className="from-info">
                        <span className="from-name">{email.from_name || email.from_email}</span>
                        <span className="from-email">{email.from_email}</span>
                      </div>
                      <div className="email-meta">
                        <span className="date">{formatDate(email.sent_date)}</span>
                        {email.matched_loan_id && (
                          <span className="match-badge loan">Loan #{email.matched_loan_id}</span>
                        )}
                        {email.matched_lead_id && (
                          <span className="match-badge lead">Lead #{email.matched_lead_id}</span>
                        )}
                      </div>
                    </div>
                    <div className="email-subject">{email.subject || '(No Subject)'}</div>
                    <div className="email-preview">{email.body_preview?.substring(0, 150)}...</div>
                    <div className="email-footer">
                      <div className="email-tags">
                        {email.has_attachments && (
                          <span className="tag attachment">📎 {email.attachment_count} files</span>
                        )}
                        {email.ai_analysis?.disposition && (
                          <span className="tag disposition">{email.ai_analysis.disposition}</span>
                        )}
                        {email.ai_analysis?.urgency_level && (
                          <span
                            className="tag urgency"
                            style={{ backgroundColor: getUrgencyLabel(email.ai_analysis.urgency_level).color }}
                          >
                            {getUrgencyLabel(email.ai_analysis.urgency_level).label}
                          </span>
                        )}
                      </div>
                      <div className="email-actions">
                        <button
                          className="action-btn view"
                          onClick={() => handleViewEmail(email)}
                        >
                          View
                        </button>
                        {email.status === 'pending' && (
                          <button
                            className="action-btn process"
                            onClick={() => handleOpenDisposition(email)}
                            disabled={processingId === email.id}
                          >
                            {processingId === email.id ? 'Processing...' : 'Process'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Conversations Tab */}
        {activeTab === 'conversations' && (
          <div className="conversations-section">
            <div className="filters-row">
              <input
                type="number"
                placeholder="Enter Loan ID to view conversation log"
                value={selectedLoanId}
                onChange={(e) => setSelectedLoanId(e.target.value)}
                className="loan-id-input"
              />
              <button className="refresh-btn" onClick={loadConversations}>
                🔍 Load Conversations
              </button>
            </div>

            {!selectedLoanId ? (
              <div className="empty-state">
                <div className="empty-icon">💬</div>
                <h3>Enter a Loan ID</h3>
                <p>View the AI-generated conversation log for any loan</p>
              </div>
            ) : loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : conversations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📝</div>
                <h3>No conversations found</h3>
                <p>No conversation logs for Loan #{selectedLoanId}</p>
              </div>
            ) : (
              <div className="conversation-list">
                {conversations.map(conv => (
                  <div key={conv.id} className="conversation-card">
                    <div className="conv-header">
                      <span className="conv-direction">{conv.direction === 'inbound' ? '📥' : '📤'} {conv.direction}</span>
                      <span className="conv-date">{formatDate(conv.email_date)}</span>
                    </div>
                    <div className="conv-subject">{conv.email_subject || '(No Subject)'}</div>
                    <div className="conv-summary">{conv.summary}</div>
                    <div className="conv-meta">
                      <span
                        className="sentiment-badge"
                        style={{ backgroundColor: getSentimentColor(conv.sentiment) }}
                      >
                        {conv.sentiment}
                      </span>
                      <span className="urgency-badge">Urgency: {conv.urgency_level}</span>
                    </div>
                    {conv.key_points && conv.key_points.length > 0 && (
                      <div className="conv-key-points">
                        <strong>Key Points:</strong>
                        <ul>
                          {(typeof conv.key_points === 'string' ? JSON.parse(conv.key_points) : conv.key_points).map((point, i) => (
                            <li key={i}>{point}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="documents-section">
            <div className="filters-row">
              <input
                type="number"
                placeholder="Enter Loan ID to view documents"
                value={docLoanId}
                onChange={(e) => setDocLoanId(e.target.value)}
                className="loan-id-input"
              />
              <button className="refresh-btn" onClick={loadDocuments}>
                🔍 Load Documents
              </button>
            </div>

            {!docLoanId ? (
              <div className="empty-state">
                <div className="empty-icon">📁</div>
                <h3>Enter a Loan ID</h3>
                <p>Track document requests and receipts for any loan</p>
              </div>
            ) : loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : documents.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📄</div>
                <h3>No documents tracked</h3>
                <p>No document tracking records for Loan #{docLoanId}</p>
              </div>
            ) : (
              <div className="document-list">
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Requested</th>
                      <th>Received</th>
                      <th>Reminders</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map(doc => (
                      <tr key={doc.id} className={`doc-row ${doc.status}`}>
                        <td className="doc-name">{doc.document_name}</td>
                        <td className="doc-type">{doc.document_type}</td>
                        <td>
                          <span className={`status-badge ${doc.status}`}>
                            {doc.status}
                          </span>
                        </td>
                        <td>{formatDate(doc.requested_date)}</td>
                        <td>{formatDate(doc.received_date)}</td>
                        <td>{doc.reminder_count || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* SLA Tab */}
        {activeTab === 'sla' && (
          <div className="sla-section">
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : slaItems.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">⏰</div>
                <h3>No SLA items</h3>
                <p>All emails are within response SLAs</p>
              </div>
            ) : (
              <div className="sla-list">
                {slaItems.map(sla => (
                  <div key={sla.id} className={`sla-card ${sla.is_overdue ? 'overdue' : ''}`}>
                    <div className="sla-header">
                      <span className={`sla-type ${sla.sla_type}`}>{sla.sla_type}</span>
                      <span className={`sla-status ${sla.status}`}>{sla.status}</span>
                    </div>
                    <div className="sla-details">
                      <div className="sla-time">
                        <strong>Due:</strong> {formatDate(sla.response_due_at)}
                      </div>
                      <div className="sla-time">
                        <strong>Received:</strong> {formatDate(sla.email_received_at)}
                      </div>
                    </div>
                    {sla.is_overdue && (
                      <div className="sla-warning">⚠️ Response overdue!</div>
                    )}
                    {sla.status === 'pending' && (
                      <button
                        className="sla-respond-btn"
                        onClick={() => handleMarkSlaResponded(sla.id)}
                      >
                        Mark as Responded
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* All Documents Tab */}
        {activeTab === 'all-documents' && (
          <div className="all-documents-section">
            <div className="section-header">
              <h3>All Received Documents</h3>
              <button className="refresh-btn" onClick={loadAllDocuments}>
                🔄 Refresh
              </button>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : allDocuments.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📄</div>
                <h3>No documents tracked</h3>
                <p>Documents will appear here as they're received via email</p>
              </div>
            ) : (
              <div className="document-list">
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Type</th>
                      <th>Loan</th>
                      <th>Status</th>
                      <th>Received</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allDocuments.map(doc => (
                      <tr key={doc.id} className={`doc-row ${doc.status}`}>
                        <td className="doc-name">{doc.document_name}</td>
                        <td className="doc-type">{doc.document_type}</td>
                        <td>
                          {doc.loan_id ? (
                            <span
                              className="loan-link"
                              onClick={() => navigate(`/loans/${doc.loan_id}`)}
                              style={{ cursor: 'pointer', color: '#3b82f6', textDecoration: 'underline' }}
                            >
                              #{doc.loan_id}
                            </span>
                          ) : (
                            <span className="no-loan">-</span>
                          )}
                        </td>
                        <td>
                          <span className={`status-badge ${doc.status}`}>
                            {doc.status}
                          </span>
                        </td>
                        <td>{formatDate(doc.received_date || doc.created_at)}</td>
                        <td className="doc-source">
                          {doc.from_email || doc.source_email || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="doc-summary">
                  Showing {allDocuments.length} of {allDocumentsTotal} documents
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Email Detail Modal */}
      {showDetailModal && selectedEmail && (
        <div className="modal-overlay" onClick={() => setShowDetailModal(false)}>
          <div className="modal-content large" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Email Details</h2>
              <button className="close-btn" onClick={() => setShowDetailModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="email-detail">
                <div className="detail-row">
                  <strong>From:</strong>
                  <span>{selectedEmail.from_name} &lt;{selectedEmail.from_email}&gt;</span>
                </div>
                <div className="detail-row">
                  <strong>To:</strong>
                  <span>{(selectedEmail.to_emails || []).join(', ')}</span>
                </div>
                <div className="detail-row">
                  <strong>Subject:</strong>
                  <span>{selectedEmail.subject}</span>
                </div>
                <div className="detail-row">
                  <strong>Date:</strong>
                  <span>{formatDate(selectedEmail.sent_date)}</span>
                </div>
                {selectedEmail.has_attachments && (
                  <div className="detail-row">
                    <strong>Attachments:</strong>
                    <span>{(selectedEmail.attachment_names || []).join(', ')}</span>
                  </div>
                )}
                <div className="detail-section">
                  <strong>Body:</strong>
                  <div className="email-body-content">
                    {selectedEmail.body_preview || selectedEmail.body_full || 'No content'}
                  </div>
                </div>
                {selectedEmail.ai_analysis && (
                  <div className="detail-section ai-analysis">
                    <strong>AI Analysis:</strong>
                    <div className="analysis-content">
                      <p><strong>Summary:</strong> {selectedEmail.ai_analysis.summary}</p>
                      <p><strong>Disposition:</strong> {selectedEmail.ai_analysis.disposition}</p>
                      <p><strong>Sentiment:</strong> {selectedEmail.ai_analysis.sentiment}</p>
                      <p><strong>Urgency:</strong> {selectedEmail.ai_analysis.urgency_level}/5</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Dialog */}
      {showDispositionDialog && dispositionEmail && (
        <div className="modal-overlay" onClick={() => setShowDispositionDialog(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Process Email</h2>
              <button className="close-btn" onClick={() => setShowDispositionDialog(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="email-preview-mini">
                <strong>{dispositionEmail.subject}</strong>
                <p>From: {dispositionEmail.from_email}</p>
              </div>

              <div className="form-group">
                <label>Disposition:</label>
                <div className="disposition-grid">
                  {dispositionOptions.map(opt => (
                    <button
                      key={opt.value}
                      className={`disposition-option ${selectedDisposition === opt.value ? 'selected' : ''}`}
                      onClick={() => setSelectedDisposition(opt.value)}
                    >
                      <span className="opt-icon">{opt.icon}</span>
                      <span className="opt-label">{opt.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={createTask}
                    onChange={(e) => setCreateTask(e.target.checked)}
                  />
                  Create follow-up task
                </label>
              </div>

              {createTask && (
                <div className="form-group">
                  <label>Task Title:</label>
                  <input
                    type="text"
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    placeholder="Enter task title"
                  />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="cancel-btn" onClick={() => setShowDispositionDialog(false)}>
                Cancel
              </button>
              <button
                className="process-btn"
                onClick={handleProcessEmail}
                disabled={!selectedDisposition || processingId}
              >
                {processingId ? 'Processing...' : 'Process Email'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default EmailIntelligence;
