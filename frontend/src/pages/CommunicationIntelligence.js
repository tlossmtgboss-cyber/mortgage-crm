import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import './CommunicationIntelligence.css';

function CommunicationIntelligence() {
  const navigate = useNavigate();

  // Communication mode: 'email' or 'sms'
  const [commMode, setCommMode] = useState('email');

  // Subtabs within each mode
  const [activeTab, setActiveTab] = useState('queue');
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState(null);

  // ================== EMAIL STATE ==================
  const [emailQueue, setEmailQueue] = useState([]);
  const [emailQueueTotal, setEmailQueueTotal] = useState(0);
  const [emailFilters, setEmailFilters] = useState({
    status: 'pending',
    disposition: '',
    hasMatch: ''
  });
  const [emailConversations, setEmailConversations] = useState([]);
  const [emailDocuments, setEmailDocuments] = useState([]);
  const [emailAllDocuments, setEmailAllDocuments] = useState([]);
  const [emailSlaItems, setEmailSlaItems] = useState([]);
  const [emailStats, setEmailStats] = useState({});
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [showEmailDetailModal, setShowEmailDetailModal] = useState(false);
  const [selectedLoanId, setSelectedLoanId] = useState('');
  const [docLoanId, setDocLoanId] = useState('');

  // ================== SMS STATE ==================
  const [smsQueue, setSmsQueue] = useState([]);
  const [smsQueueTotal, setSmsQueueTotal] = useState(0);
  const [smsFilters, setSmsFilters] = useState({
    status: 'pending',
    disposition: '',
    direction: '',
    requiresResponse: ''
  });
  const [smsConversations, setSmsConversations] = useState([]);
  const [smsTemplates, setSmsTemplates] = useState([]);
  const [smsOptOuts, setSmsOptOuts] = useState([]);
  const [smsSlaItems, setSmsSlaItems] = useState([]);
  const [smsDocMentions, setSmsDocMentions] = useState([]);
  const [smsStats, setSmsStats] = useState({});
  const [selectedSms, setSelectedSms] = useState(null);
  const [showSmsDetailModal, setShowSmsDetailModal] = useState(false);
  const [smsPhoneFilter, setSmsPhoneFilter] = useState('');

  // ================== DISPOSITION DIALOG ==================
  const [showDispositionDialog, setShowDispositionDialog] = useState(false);
  const [dispositionItem, setDispositionItem] = useState(null);
  const [selectedDisposition, setSelectedDisposition] = useState('');
  const [createTask, setCreateTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');

  const emailDispositionOptions = [
    { value: 'document_received', label: 'Document Received', icon: '📄' },
    { value: 'document_request', label: 'Document Request', icon: '📋' },
    { value: 'action_required', label: 'Action Required', icon: '⚡' },
    { value: 'general_correspondence', label: 'General Correspondence', icon: '💬' },
    { value: 'status_update', label: 'Status Update', icon: '📊' },
    { value: 'rate_lock_request', label: 'Rate Lock Request', icon: '🔒' },
    { value: 'closing_related', label: 'Closing Related', icon: '🏠' },
    { value: 'skip', label: 'Skip/Archive', icon: '⏭️' }
  ];

  const smsDispositionOptions = [
    { value: 'general_correspondence', label: 'General', icon: '💬' },
    { value: 'document_mention', label: 'Document Mention', icon: '📄' },
    { value: 'appointment_related', label: 'Appointment', icon: '📅' },
    { value: 'status_inquiry', label: 'Status Question', icon: '❓' },
    { value: 'action_required', label: 'Action Required', icon: '⚡' },
    { value: 'opt_out', label: 'Opt-Out', icon: '🚫' },
    { value: 'processed', label: 'Processed', icon: '✅' },
    { value: 'skip', label: 'Skip', icon: '⏭️' }
  ];

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  // Reset tab when switching modes
  useEffect(() => {
    setActiveTab('queue');
  }, [commMode]);

  // Load data when mode or tab changes
  useEffect(() => {
    loadData();
    loadStats();
  }, [commMode, activeTab, emailFilters, smsFilters, selectedLoanId, docLoanId]);

  const loadStats = async () => {
    try {
      if (commMode === 'email') {
        const response = await fetch(`${API_BASE_URL}/api/v1/email-intelligence/stats`, {
          headers: getAuthHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          setEmailStats(data);
        }
      } else {
        const response = await fetch(`${API_BASE_URL}/api/v1/sms-intelligence/stats`, {
          headers: getAuthHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          setSmsStats(data);
        }
      }
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      if (commMode === 'email') {
        switch (activeTab) {
          case 'queue': await loadEmailQueue(); break;
          case 'conversations': await loadEmailConversations(); break;
          case 'documents': await loadEmailDocuments(); break;
          case 'all-documents': await loadAllEmailDocuments(); break;
          case 'sla': await loadEmailSlaItems(); break;
        }
      } else {
        switch (activeTab) {
          case 'queue': await loadSmsQueue(); break;
          case 'conversations': await loadSmsConversations(); break;
          case 'templates': await loadSmsTemplates(); break;
          case 'opt-outs': await loadSmsOptOuts(); break;
          case 'sla': await loadSmsSlaItems(); break;
          case 'doc-mentions': await loadSmsDocMentions(); break;
        }
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  // ================== EMAIL LOADERS ==================
  const loadEmailQueue = async () => {
    try {
      let url = `${API_BASE_URL}/api/v1/email-intelligence/queue?limit=50`;
      if (emailFilters.status) url += `&status=${emailFilters.status}`;
      if (emailFilters.disposition) url += `&disposition=${emailFilters.disposition}`;
      if (emailFilters.hasMatch === 'yes') url += `&has_match=true`;
      if (emailFilters.hasMatch === 'no') url += `&has_match=false`;

      const response = await fetch(url, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setEmailQueue(data.emails || []);
        setEmailQueueTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Error loading email queue:', error);
    }
  };

  const loadEmailConversations = async () => {
    if (!selectedLoanId) {
      setEmailConversations([]);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/email-intelligence/conversation-log/loan/${selectedLoanId}?limit=50`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setEmailConversations(data.entries || []);
      }
    } catch (error) {
      console.error('Error loading conversations:', error);
    }
  };

  const loadEmailDocuments = async () => {
    if (!docLoanId) {
      setEmailDocuments([]);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/email-intelligence/document-tracking/loan/${docLoanId}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setEmailDocuments(data.documents || []);
      }
    } catch (error) {
      console.error('Error loading documents:', error);
    }
  };

  const loadAllEmailDocuments = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/email-intelligence/document-tracking/all?limit=100`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setEmailAllDocuments(data.documents || []);
      }
    } catch (error) {
      console.error('Error loading all documents:', error);
    }
  };

  const loadEmailSlaItems = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/email-intelligence/sla-tracking`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setEmailSlaItems(data.slas || []);
      }
    } catch (error) {
      console.error('Error loading SLA items:', error);
    }
  };

  // ================== SMS LOADERS ==================
  const loadSmsQueue = async () => {
    try {
      let url = `${API_BASE_URL}/api/v1/sms-intelligence/queue?limit=50`;
      if (smsFilters.status) url += `&status=${smsFilters.status}`;
      if (smsFilters.disposition) url += `&disposition=${smsFilters.disposition}`;
      if (smsFilters.direction) url += `&direction=${smsFilters.direction}`;
      if (smsFilters.requiresResponse === 'yes') url += `&requires_response=true`;

      const response = await fetch(url, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        setSmsQueue(data.items || []);
        setSmsQueueTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Error loading SMS queue:', error);
    }
  };

  const loadSmsConversations = async () => {
    if (!smsPhoneFilter) {
      setSmsConversations([]);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/conversation/${encodeURIComponent(smsPhoneFilter)}?limit=50`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSmsConversations(data.conversations || []);
      }
    } catch (error) {
      console.error('Error loading SMS conversations:', error);
    }
  };

  const loadSmsTemplates = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/templates`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSmsTemplates(data.templates || []);
      }
    } catch (error) {
      console.error('Error loading SMS templates:', error);
    }
  };

  const loadSmsOptOuts = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/opt-outs?limit=100`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSmsOptOuts(data.opt_outs || []);
      }
    } catch (error) {
      console.error('Error loading opt-outs:', error);
    }
  };

  const loadSmsSlaItems = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/sla/pending`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSmsSlaItems(data.pending_sla || []);
      }
    } catch (error) {
      console.error('Error loading SMS SLA items:', error);
    }
  };

  const loadSmsDocMentions = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/document-mentions?limit=50`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setSmsDocMentions(data.document_mentions || []);
      }
    } catch (error) {
      console.error('Error loading document mentions:', error);
    }
  };

  // ================== HANDLERS ==================
  const handleViewEmail = (email) => {
    setSelectedEmail(email);
    setShowEmailDetailModal(true);
  };

  const handleViewSms = (sms) => {
    setSelectedSms(sms);
    setShowSmsDetailModal(true);
  };

  const handleOpenEmailDisposition = (email) => {
    setDispositionItem({ type: 'email', data: email });
    setSelectedDisposition(email.ai_analysis?.disposition || 'general_correspondence');
    setCreateTask(false);
    setTaskTitle(`Follow up: ${email.subject || 'Email'}`);
    setShowDispositionDialog(true);
  };

  const handleOpenSmsDisposition = (sms) => {
    setDispositionItem({ type: 'sms', data: sms });
    setSelectedDisposition(sms.ai_analysis?.disposition || sms.disposition || 'general_correspondence');
    setCreateTask(false);
    setTaskTitle(`Follow up: SMS from ${sms.from_phone}`);
    setShowDispositionDialog(true);
  };

  const handleProcessDisposition = async () => {
    if (!dispositionItem || !selectedDisposition) return;

    setProcessingId(dispositionItem.data.id);
    try {
      if (dispositionItem.type === 'email') {
        let url = `${API_BASE_URL}/api/v1/email-intelligence/queue/${dispositionItem.data.id}/process-with-intelligence?disposition=${selectedDisposition}`;
        if (createTask) {
          url += `&create_task=true&task_title=${encodeURIComponent(taskTitle)}`;
        }
        const response = await fetch(url, { method: 'POST', headers: getAuthHeaders() });
        if (response.ok) {
          setShowDispositionDialog(false);
          setDispositionItem(null);
          loadData();
          loadStats();
        } else {
          const error = await response.json();
          alert(`Error: ${error.detail || error.error || 'Failed to process'}`);
        }
      } else {
        // SMS disposition
        const response = await fetch(
          `${API_BASE_URL}/api/v1/sms-intelligence/queue/${dispositionItem.data.id}/disposition`,
          {
            method: 'PUT',
            headers: getAuthHeaders(),
            body: JSON.stringify({
              sms_id: dispositionItem.data.id,
              disposition: selectedDisposition,
              processing_notes: taskTitle || null
            })
          }
        );
        if (response.ok) {
          setShowDispositionDialog(false);
          setDispositionItem(null);
          loadData();
          loadStats();
        } else {
          const error = await response.json();
          alert(`Error: ${error.detail || error.error || 'Failed to process'}`);
        }
      }
    } catch (error) {
      console.error('Error processing:', error);
      alert('Failed to process');
    } finally {
      setProcessingId(null);
    }
  };

  const handleMarkSlaResponded = async (slaId, type) => {
    try {
      const url = type === 'email'
        ? `${API_BASE_URL}/api/v1/email-intelligence/sla-tracking/${slaId}/respond`
        : `${API_BASE_URL}/api/v1/sms-intelligence/sla/${slaId}/respond`;
      const response = await fetch(url, { method: 'POST', headers: getAuthHeaders() });
      if (response.ok) {
        loadData();
        loadStats();
      }
    } catch (error) {
      console.error('Error marking SLA responded:', error);
    }
  };

  // ================== UTILITIES ==================
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

  const formatPhone = (phone) => {
    if (!phone) return '-';
    // Format +1XXXXXXXXXX to (XXX) XXX-XXXX
    const digits = phone.replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('1')) {
      return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
    }
    if (digits.length === 10) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    }
    return phone;
  };

  // ================== RENDER ==================
  const currentStats = commMode === 'email' ? emailStats : smsStats;
  const currentDispositionOptions = commMode === 'email' ? emailDispositionOptions : smsDispositionOptions;

  return (
    <div className="communication-intelligence-page">
      {/* Page Header */}
      <div className="page-header">
        <h1>Communication Intelligence</h1>
        <p className="subtitle">AI-powered email & SMS analysis, conversation tracking, and document management</p>
      </div>

      {/* Mode Selector */}
      <div className="mode-selector">
        <button
          className={`mode-btn ${commMode === 'email' ? 'active' : ''}`}
          onClick={() => setCommMode('email')}
        >
          <span className="mode-icon">📧</span>
          <span className="mode-label">Email</span>
          {emailStats.pending_count > 0 && (
            <span className="mode-badge">{emailStats.pending_count}</span>
          )}
        </button>
        <button
          className={`mode-btn ${commMode === 'sms' ? 'active' : ''}`}
          onClick={() => setCommMode('sms')}
        >
          <span className="mode-icon">💬</span>
          <span className="mode-label">SMS</span>
          {smsStats.totals?.pending > 0 && (
            <span className="mode-badge">{smsStats.totals.pending}</span>
          )}
        </button>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        {commMode === 'email' ? (
          <>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'pending' }); setActiveTab('queue'); }}>
              <div className="stat-value">{emailStats.pending_count || 0}</div>
              <div className="stat-label">Pending</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'processed' }); setActiveTab('queue'); }}>
              <div className="stat-value">{emailStats.processed_count || 0}</div>
              <div className="stat-label">Processed</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('conversations')}>
              <div className="stat-value">{emailStats.conversation_logs_created || 0}</div>
              <div className="stat-label">Conversations</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('all-documents')}>
              <div className="stat-value">{emailStats.documents_received || 0}</div>
              <div className="stat-label">Docs Received</div>
            </div>
          </>
        ) : (
          <>
            <div className="stat-card clickable" onClick={() => { setSmsFilters({ ...smsFilters, status: 'pending' }); setActiveTab('queue'); }}>
              <div className="stat-value">{smsStats.totals?.pending || 0}</div>
              <div className="stat-label">Pending</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setSmsFilters({ ...smsFilters, requiresResponse: 'yes' }); setActiveTab('queue'); }}>
              <div className="stat-value">{smsStats.totals?.needs_response || 0}</div>
              <div className="stat-label">Need Response</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('opt-outs')}>
              <div className="stat-value">{smsStats.totals?.opt_outs || 0}</div>
              <div className="stat-label">Opt-Outs</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('sla')}>
              <div className="stat-value">{smsStats.sla?.breached || 0}</div>
              <div className="stat-label">SLA Breached</div>
            </div>
          </>
        )}
      </div>

      {/* Tabs */}
      <div className="tabs-container">
        {commMode === 'email' ? (
          <>
            <button className={`tab-button ${activeTab === 'queue' ? 'active' : ''}`} onClick={() => setActiveTab('queue')}>
              Queue ({emailStats.pending_count || 0})
            </button>
            <button className={`tab-button ${activeTab === 'conversations' ? 'active' : ''}`} onClick={() => setActiveTab('conversations')}>
              Conversations
            </button>
            <button className={`tab-button ${activeTab === 'documents' ? 'active' : ''}`} onClick={() => setActiveTab('documents')}>
              Documents
            </button>
            <button className={`tab-button ${activeTab === 'sla' ? 'active' : ''}`} onClick={() => setActiveTab('sla')}>
              SLA Tracking
            </button>
            <button className={`tab-button ${activeTab === 'all-documents' ? 'active' : ''}`} onClick={() => setActiveTab('all-documents')}>
              All Docs ({emailStats.documents_received || 0})
            </button>
          </>
        ) : (
          <>
            <button className={`tab-button ${activeTab === 'queue' ? 'active' : ''}`} onClick={() => setActiveTab('queue')}>
              Queue ({smsStats.totals?.pending || 0})
            </button>
            <button className={`tab-button ${activeTab === 'conversations' ? 'active' : ''}`} onClick={() => setActiveTab('conversations')}>
              Conversations
            </button>
            <button className={`tab-button ${activeTab === 'templates' ? 'active' : ''}`} onClick={() => setActiveTab('templates')}>
              Templates
            </button>
            <button className={`tab-button ${activeTab === 'opt-outs' ? 'active' : ''}`} onClick={() => setActiveTab('opt-outs')}>
              Opt-Outs
            </button>
            <button className={`tab-button ${activeTab === 'sla' ? 'active' : ''}`} onClick={() => setActiveTab('sla')}>
              SLA Pending
            </button>
            <button className={`tab-button ${activeTab === 'doc-mentions' ? 'active' : ''}`} onClick={() => setActiveTab('doc-mentions')}>
              Doc Mentions
            </button>
          </>
        )}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* ================== EMAIL TABS ================== */}
        {commMode === 'email' && activeTab === 'queue' && (
          <div className="queue-section">
            <div className="filters-row">
              <select value={emailFilters.status} onChange={(e) => setEmailFilters({ ...emailFilters, status: e.target.value })}>
                <option value="">All Status</option>
                <option value="pending">Pending</option>
                <option value="processed">Processed</option>
              </select>
              <select value={emailFilters.disposition} onChange={(e) => setEmailFilters({ ...emailFilters, disposition: e.target.value })}>
                <option value="">All Dispositions</option>
                {emailDispositionOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <select value={emailFilters.hasMatch} onChange={(e) => setEmailFilters({ ...emailFilters, hasMatch: e.target.value })}>
                <option value="">Match Status</option>
                <option value="yes">Has Match</option>
                <option value="no">No Match</option>
              </select>
              <button className="refresh-btn" onClick={loadData}>🔄 Refresh</button>
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
              <div className="item-list">
                {emailQueue.map(email => (
                  <div key={email.id} className={`item-card ${email.status}`}>
                    <div className="item-header">
                      <div className="from-info">
                        <span className="from-name">{email.from_name || email.from_email}</span>
                        <span className="from-email">{email.from_email}</span>
                      </div>
                      <div className="item-meta">
                        <span className="date">{formatDate(email.sent_date)}</span>
                        {email.matched_loan_id && <span className="match-badge loan">Loan #{email.matched_loan_id}</span>}
                        {email.matched_lead_id && <span className="match-badge lead">Lead #{email.matched_lead_id}</span>}
                      </div>
                    </div>
                    <div className="item-subject">{email.subject || '(No Subject)'}</div>
                    <div className="item-preview">{email.body_preview?.substring(0, 150)}...</div>
                    <div className="item-footer">
                      <div className="item-tags">
                        {email.has_attachments && <span className="tag attachment">📎 {email.attachment_count}</span>}
                        {email.ai_analysis?.disposition && <span className="tag disposition">{email.ai_analysis.disposition}</span>}
                        {email.ai_analysis?.urgency_level && (
                          <span className="tag urgency" style={{ backgroundColor: getUrgencyLabel(email.ai_analysis.urgency_level).color }}>
                            {getUrgencyLabel(email.ai_analysis.urgency_level).label}
                          </span>
                        )}
                      </div>
                      <div className="item-actions">
                        <button className="action-btn view" onClick={() => handleViewEmail(email)}>View</button>
                        {email.status === 'pending' && (
                          <button className="action-btn process" onClick={() => handleOpenEmailDisposition(email)} disabled={processingId === email.id}>
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

        {commMode === 'email' && activeTab === 'conversations' && (
          <div className="conversations-section">
            <div className="filters-row">
              <input
                type="number"
                placeholder="Enter Loan ID to view conversation log"
                value={selectedLoanId}
                onChange={(e) => setSelectedLoanId(e.target.value)}
                className="loan-id-input"
              />
              <button className="refresh-btn" onClick={loadEmailConversations}>🔍 Load Conversations</button>
            </div>
            {!selectedLoanId ? (
              <div className="empty-state">
                <div className="empty-icon">💬</div>
                <h3>Enter a Loan ID</h3>
                <p>View the AI-generated conversation log for any loan</p>
              </div>
            ) : loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : emailConversations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📝</div>
                <h3>No conversations found</h3>
                <p>No conversation logs for Loan #{selectedLoanId}</p>
              </div>
            ) : (
              <div className="conversation-list">
                {emailConversations.map(conv => (
                  <div key={conv.id} className="conversation-card">
                    <div className="conv-header">
                      <span className="conv-direction">{conv.direction === 'inbound' ? '📥' : '📤'} {conv.direction}</span>
                      <span className="conv-date">{formatDate(conv.email_date)}</span>
                    </div>
                    <div className="conv-subject">{conv.email_subject || '(No Subject)'}</div>
                    <div className="conv-summary">{conv.summary}</div>
                    <div className="conv-meta">
                      <span className="sentiment-badge" style={{ backgroundColor: getSentimentColor(conv.sentiment) }}>{conv.sentiment}</span>
                      <span className="urgency-badge">Urgency: {conv.urgency_level}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {commMode === 'email' && activeTab === 'documents' && (
          <div className="documents-section">
            <div className="filters-row">
              <input type="number" placeholder="Enter Loan ID" value={docLoanId} onChange={(e) => setDocLoanId(e.target.value)} className="loan-id-input" />
              <button className="refresh-btn" onClick={loadEmailDocuments}>🔍 Load Documents</button>
            </div>
            {!docLoanId ? (
              <div className="empty-state"><div className="empty-icon">📁</div><h3>Enter a Loan ID</h3></div>
            ) : loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : emailDocuments.length === 0 ? (
              <div className="empty-state"><div className="empty-icon">📄</div><h3>No documents tracked</h3></div>
            ) : (
              <div className="document-list">
                <table className="doc-table">
                  <thead><tr><th>Document</th><th>Type</th><th>Status</th><th>Requested</th><th>Received</th></tr></thead>
                  <tbody>
                    {emailDocuments.map(doc => (
                      <tr key={doc.id} className={`doc-row ${doc.status}`}>
                        <td>{doc.document_name}</td>
                        <td>{doc.document_type}</td>
                        <td><span className={`status-badge ${doc.status}`}>{doc.status}</span></td>
                        <td>{formatDate(doc.requested_date)}</td>
                        <td>{formatDate(doc.received_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {commMode === 'email' && activeTab === 'all-documents' && (
          <div className="all-documents-section">
            <div className="section-header">
              <h3>All Received Documents</h3>
              <button className="refresh-btn" onClick={loadAllEmailDocuments}>🔄 Refresh</button>
            </div>
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : emailAllDocuments.length === 0 ? (
              <div className="empty-state"><div className="empty-icon">📄</div><h3>No documents tracked</h3></div>
            ) : (
              <div className="document-list">
                <table className="doc-table">
                  <thead><tr><th>Document</th><th>Type</th><th>Loan</th><th>Status</th><th>Received</th></tr></thead>
                  <tbody>
                    {emailAllDocuments.map(doc => (
                      <tr key={doc.id} className={`doc-row ${doc.status}`}>
                        <td>{doc.document_name}</td>
                        <td>{doc.document_type}</td>
                        <td>{doc.loan_id ? <span className="loan-link" onClick={() => navigate(`/loans/${doc.loan_id}`)}>#{doc.loan_id}</span> : '-'}</td>
                        <td><span className={`status-badge ${doc.status}`}>{doc.status}</span></td>
                        <td>{formatDate(doc.received_date || doc.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {commMode === 'email' && activeTab === 'sla' && (
          <div className="sla-section">
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : emailSlaItems.length === 0 ? (
              <div className="empty-state"><div className="empty-icon">⏰</div><h3>All caught up!</h3><p>No pending SLA items</p></div>
            ) : (
              <div className="sla-list">
                {emailSlaItems.map(sla => (
                  <div key={sla.id} className={`sla-card ${sla.is_overdue ? 'overdue' : ''}`}>
                    <div className="sla-header">
                      <span className={`sla-type ${sla.sla_type}`}>{sla.sla_type}</span>
                      <span className={`sla-status ${sla.status}`}>{sla.status}</span>
                    </div>
                    <div className="sla-details">
                      <div><strong>Due:</strong> {formatDate(sla.response_due_at)}</div>
                      <div><strong>Received:</strong> {formatDate(sla.email_received_at)}</div>
                    </div>
                    {sla.status === 'pending' && (
                      <button className="sla-respond-btn" onClick={() => handleMarkSlaResponded(sla.id, 'email')}>Mark Responded</button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ================== SMS TABS ================== */}
        {commMode === 'sms' && activeTab === 'queue' && (
          <div className="queue-section">
            <div className="filters-row">
              <select value={smsFilters.status} onChange={(e) => setSmsFilters({ ...smsFilters, status: e.target.value })}>
                <option value="">All Status</option>
                <option value="pending">Pending</option>
                <option value="analyzed">Analyzed</option>
                <option value="completed">Completed</option>
              </select>
              <select value={smsFilters.direction} onChange={(e) => setSmsFilters({ ...smsFilters, direction: e.target.value })}>
                <option value="">All Directions</option>
                <option value="inbound">Inbound</option>
                <option value="outbound">Outbound</option>
              </select>
              <select value={smsFilters.disposition} onChange={(e) => setSmsFilters({ ...smsFilters, disposition: e.target.value })}>
                <option value="">All Dispositions</option>
                {smsDispositionOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <select value={smsFilters.requiresResponse} onChange={(e) => setSmsFilters({ ...smsFilters, requiresResponse: e.target.value })}>
                <option value="">Response Status</option>
                <option value="yes">Needs Response</option>
              </select>
              <button className="refresh-btn" onClick={loadData}>🔄 Refresh</button>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsQueue.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">💬</div>
                <h3>No SMS messages in queue</h3>
                <p>Messages will appear here when received via Twilio webhook</p>
              </div>
            ) : (
              <div className="item-list">
                {smsQueue.map(sms => (
                  <div key={sms.id} className={`item-card sms ${sms.status} ${sms.is_priority ? 'priority' : ''}`}>
                    <div className="item-header">
                      <div className="from-info">
                        <span className="from-name">
                          {sms.direction === 'inbound' ? '📥' : '📤'} {formatPhone(sms.direction === 'inbound' ? sms.from_phone : sms.to_phone)}
                        </span>
                        {sms.loan_borrower_name && <span className="from-email">{sms.loan_borrower_name}</span>}
                        {sms.lead_name && <span className="from-email">{sms.lead_name}</span>}
                      </div>
                      <div className="item-meta">
                        <span className="date">{formatDate(sms.sent_at || sms.received_at)}</span>
                        {sms.matched_loan_id && <span className="match-badge loan">Loan #{sms.matched_loan_id}</span>}
                        {sms.matched_lead_id && <span className="match-badge lead">Lead #{sms.matched_lead_id}</span>}
                      </div>
                    </div>
                    <div className="item-preview sms-body">{sms.message_body}</div>
                    <div className="item-footer">
                      <div className="item-tags">
                        {sms.has_media && <span className="tag attachment">📷 {sms.media_count} media</span>}
                        {sms.disposition && <span className="tag disposition">{sms.disposition}</span>}
                        {sms.requires_response && <span className="tag response-needed">Response Needed</span>}
                        {sms.is_opt_out && <span className="tag opt-out">OPT-OUT</span>}
                        {sms.is_priority && <span className="tag priority">Priority</span>}
                        {sms.ai_analysis?.sentiment && (
                          <span className="tag sentiment" style={{ backgroundColor: getSentimentColor(sms.ai_analysis.sentiment) }}>
                            {sms.ai_analysis.sentiment}
                          </span>
                        )}
                      </div>
                      <div className="item-actions">
                        <button className="action-btn view" onClick={() => handleViewSms(sms)}>View</button>
                        {sms.status !== 'completed' && (
                          <button className="action-btn process" onClick={() => handleOpenSmsDisposition(sms)} disabled={processingId === sms.id}>
                            {processingId === sms.id ? 'Processing...' : 'Process'}
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

        {commMode === 'sms' && activeTab === 'conversations' && (
          <div className="conversations-section">
            <div className="filters-row">
              <input
                type="tel"
                placeholder="Enter phone number (e.g., +15551234567)"
                value={smsPhoneFilter}
                onChange={(e) => setSmsPhoneFilter(e.target.value)}
                className="phone-input"
              />
              <button className="refresh-btn" onClick={loadSmsConversations}>🔍 Load Conversations</button>
            </div>
            {!smsPhoneFilter ? (
              <div className="empty-state">
                <div className="empty-icon">💬</div>
                <h3>Enter a Phone Number</h3>
                <p>View the SMS conversation history for any phone number</p>
              </div>
            ) : loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsConversations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📝</div>
                <h3>No conversations found</h3>
                <p>No SMS history for {formatPhone(smsPhoneFilter)}</p>
              </div>
            ) : (
              <div className="conversation-list sms-thread">
                {smsConversations.map(conv => (
                  <div key={conv.id} className={`sms-bubble ${conv.direction}`}>
                    <div className="bubble-content">{conv.message_body}</div>
                    <div className="bubble-meta">
                      <span className="bubble-time">{formatDate(conv.message_date)}</span>
                      {conv.intent && <span className="bubble-intent">{conv.intent}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {commMode === 'sms' && activeTab === 'templates' && (
          <div className="templates-section">
            <div className="section-header">
              <h3>SMS Templates</h3>
              <button className="refresh-btn" onClick={loadSmsTemplates}>🔄 Refresh</button>
            </div>
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsTemplates.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📝</div>
                <h3>No templates yet</h3>
                <p>Create SMS templates for quick responses</p>
              </div>
            ) : (
              <div className="templates-grid">
                {smsTemplates.map(template => (
                  <div key={template.id} className="template-card">
                    <div className="template-header">
                      <span className="template-name">{template.name}</span>
                      <span className="template-category">{template.category}</span>
                    </div>
                    <div className="template-body">{template.template_body}</div>
                    <div className="template-footer">
                      <span className="template-usage">Used {template.times_used}x</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {commMode === 'sms' && activeTab === 'opt-outs' && (
          <div className="opt-outs-section">
            <div className="section-header">
              <h3>Opted-Out Phone Numbers</h3>
              <button className="refresh-btn" onClick={loadSmsOptOuts}>🔄 Refresh</button>
            </div>
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsOptOuts.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">✅</div>
                <h3>No opt-outs</h3>
                <p>All contacts are subscribed to SMS</p>
              </div>
            ) : (
              <div className="opt-outs-list">
                <table className="doc-table">
                  <thead><tr><th>Phone Number</th><th>Opted Out</th><th>Message</th><th>Linked Entity</th></tr></thead>
                  <tbody>
                    {smsOptOuts.map((opt, i) => (
                      <tr key={i}>
                        <td className="phone-cell">{formatPhone(opt.phone_number)}</td>
                        <td>{formatDate(opt.opted_out_at)}</td>
                        <td className="opt-message">{opt.opt_out_message || '-'}</td>
                        <td>
                          {opt.loan_id && <span className="match-badge loan">Loan #{opt.loan_id}</span>}
                          {opt.lead_id && <span className="match-badge lead">Lead #{opt.lead_id}</span>}
                          {!opt.loan_id && !opt.lead_id && '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {commMode === 'sms' && activeTab === 'sla' && (
          <div className="sla-section">
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsSlaItems.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">⏰</div>
                <h3>All caught up!</h3>
                <p>No pending SMS SLAs</p>
              </div>
            ) : (
              <div className="sla-list">
                {smsSlaItems.map(sla => (
                  <div key={sla.id} className={`sla-card ${new Date(sla.response_due_at) < new Date() ? 'overdue' : ''}`}>
                    <div className="sla-header">
                      <span className="sla-type">{sla.sla_type} ({sla.sla_minutes} min)</span>
                      <span className={`sla-status ${sla.status}`}>{sla.status}</span>
                    </div>
                    <div className="sla-phone">{formatPhone(sla.phone_number)}</div>
                    <div className="sla-details">
                      <div><strong>Due:</strong> {formatDate(sla.response_due_at)}</div>
                      <div><strong>Received:</strong> {formatDate(sla.message_received_at)}</div>
                    </div>
                    {sla.message_body && <div className="sla-message">"{sla.message_body?.substring(0, 100)}..."</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {commMode === 'sms' && activeTab === 'doc-mentions' && (
          <div className="doc-mentions-section">
            <div className="section-header">
              <h3>Document Mentions in SMS</h3>
              <button className="refresh-btn" onClick={loadSmsDocMentions}>🔄 Refresh</button>
            </div>
            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsDocMentions.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📄</div>
                <h3>No document mentions</h3>
                <p>When borrowers mention documents in SMS, they'll appear here</p>
              </div>
            ) : (
              <div className="document-list">
                <table className="doc-table">
                  <thead><tr><th>Document</th><th>Type</th><th>Context</th><th>Status</th><th>Mentioned</th></tr></thead>
                  <tbody>
                    {smsDocMentions.map(doc => (
                      <tr key={doc.id}>
                        <td>{doc.document_mentioned}</td>
                        <td>{doc.document_type || '-'}</td>
                        <td className="context-cell">"{doc.mention_context?.substring(0, 50)}..."</td>
                        <td><span className={`status-badge ${doc.status}`}>{doc.status}</span></td>
                        <td>{formatDate(doc.mentioned_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Email Detail Modal */}
      {showEmailDetailModal && selectedEmail && (
        <div className="modal-overlay" onClick={() => setShowEmailDetailModal(false)}>
          <div className="modal-content large" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Email Details</h2>
              <button className="close-btn" onClick={() => setShowEmailDetailModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="email-detail">
                <div className="detail-row"><strong>From:</strong> {selectedEmail.from_name} &lt;{selectedEmail.from_email}&gt;</div>
                <div className="detail-row"><strong>To:</strong> {(selectedEmail.to_emails || []).join(', ')}</div>
                <div className="detail-row"><strong>Subject:</strong> {selectedEmail.subject}</div>
                <div className="detail-row"><strong>Date:</strong> {formatDate(selectedEmail.sent_date)}</div>
                {selectedEmail.has_attachments && (
                  <div className="detail-row"><strong>Attachments:</strong> {(selectedEmail.attachment_names || []).join(', ')}</div>
                )}
                <div className="detail-section">
                  <strong>Body:</strong>
                  <div className="email-body-content">{selectedEmail.body_preview || selectedEmail.body_full || 'No content'}</div>
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

      {/* SMS Detail Modal */}
      {showSmsDetailModal && selectedSms && (
        <div className="modal-overlay" onClick={() => setShowSmsDetailModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>SMS Details</h2>
              <button className="close-btn" onClick={() => setShowSmsDetailModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="sms-detail">
                <div className="detail-row"><strong>From:</strong> {formatPhone(selectedSms.from_phone)}</div>
                <div className="detail-row"><strong>To:</strong> {formatPhone(selectedSms.to_phone)}</div>
                <div className="detail-row"><strong>Direction:</strong> {selectedSms.direction}</div>
                <div className="detail-row"><strong>Date:</strong> {formatDate(selectedSms.sent_at || selectedSms.received_at)}</div>
                <div className="detail-section">
                  <strong>Message:</strong>
                  <div className="sms-body-content">{selectedSms.message_body}</div>
                </div>
                {selectedSms.has_media && (
                  <div className="detail-row"><strong>Media:</strong> {selectedSms.media_count} attachment(s)</div>
                )}
                {selectedSms.ai_analysis && (
                  <div className="detail-section ai-analysis">
                    <strong>AI Analysis:</strong>
                    <div className="analysis-content">
                      <p><strong>Intent:</strong> {selectedSms.ai_analysis.intent}</p>
                      <p><strong>Disposition:</strong> {selectedSms.ai_analysis.disposition}</p>
                      <p><strong>Sentiment:</strong> {selectedSms.ai_analysis.sentiment}</p>
                      <p><strong>Urgency:</strong> {selectedSms.ai_analysis.urgency_level}/5</p>
                      {selectedSms.ai_analysis.documents_mentioned?.length > 0 && (
                        <p><strong>Documents Mentioned:</strong> {selectedSms.ai_analysis.documents_mentioned.join(', ')}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Disposition Dialog */}
      {showDispositionDialog && dispositionItem && (
        <div className="modal-overlay" onClick={() => setShowDispositionDialog(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Process {dispositionItem.type === 'email' ? 'Email' : 'SMS'}</h2>
              <button className="close-btn" onClick={() => setShowDispositionDialog(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="item-preview-mini">
                <strong>{dispositionItem.type === 'email' ? dispositionItem.data.subject : formatPhone(dispositionItem.data.from_phone)}</strong>
                <p>{dispositionItem.type === 'email' ? `From: ${dispositionItem.data.from_email}` : dispositionItem.data.message_body?.substring(0, 100)}</p>
              </div>

              <div className="form-group">
                <label>Disposition:</label>
                <div className="disposition-grid">
                  {currentDispositionOptions.map(opt => (
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

              {dispositionItem.type === 'email' && (
                <div className="form-group checkbox-group">
                  <label>
                    <input type="checkbox" checked={createTask} onChange={(e) => setCreateTask(e.target.checked)} />
                    Create follow-up task
                  </label>
                </div>
              )}

              {createTask && (
                <div className="form-group">
                  <label>Task Title:</label>
                  <input type="text" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="Enter task title" />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="cancel-btn" onClick={() => setShowDispositionDialog(false)}>Cancel</button>
              <button className="process-btn" onClick={handleProcessDisposition} disabled={!selectedDisposition || processingId}>
                {processingId ? 'Processing...' : 'Process'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CommunicationIntelligence;
