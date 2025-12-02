import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import PowerDialer from './PowerDialer';
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
  const [smsPhoneFilter, setSmsPhoneFilter] = useState('');

  // ================== DETAIL PANEL STATE ==================
  const [selectedDisposition, setSelectedDisposition] = useState('');
  const [createTask, setCreateTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');

  // ================== BULK DELETE STATE ==================
  const [selectedEmailIds, setSelectedEmailIds] = useState(new Set());
  const [selectedSmsIds, setSelectedSmsIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const emailDispositionOptions = [
    { value: 'document_received', label: 'Document Received' },
    { value: 'document_request', label: 'Document Request' },
    { value: 'action_required', label: 'Action Required' },
    { value: 'general_correspondence', label: 'General Correspondence' },
    { value: 'status_update', label: 'Status Update' },
    { value: 'rate_lock_request', label: 'Rate Lock Request' },
    { value: 'closing_related', label: 'Closing Related' },
    { value: 'skip', label: 'Skip/Archive' }
  ];

  const smsDispositionOptions = [
    { value: 'general_correspondence', label: 'General' },
    { value: 'document_mention', label: 'Document Mention' },
    { value: 'appointment_related', label: 'Appointment' },
    { value: 'status_inquiry', label: 'Status Question' },
    { value: 'action_required', label: 'Action Required' },
    { value: 'opt_out', label: 'Opt-Out' },
    { value: 'processed', label: 'Processed' },
    { value: 'skip', label: 'Skip' }
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
    setSelectedEmail(null);
    setSelectedSms(null);
  }, [commMode]);

  // Load data when mode or tab changes
  useEffect(() => {
    loadData();
    loadStats();
  }, [commMode, activeTab, emailFilters, smsFilters, selectedLoanId, docLoanId]);

  // Update disposition when selection changes
  useEffect(() => {
    if (selectedEmail) {
      setSelectedDisposition(selectedEmail.ai_analysis?.disposition || 'general_correspondence');
      setTaskTitle(`Follow up: ${selectedEmail.subject || 'Email'}`);
    } else if (selectedSms) {
      setSelectedDisposition(selectedSms.ai_analysis?.disposition || selectedSms.disposition || 'general_correspondence');
      setTaskTitle(`Follow up: SMS from ${selectedSms.from_phone}`);
    }
    setCreateTask(false);
  }, [selectedEmail, selectedSms]);

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
        const emails = data.emails || [];
        setEmailQueue(emails);
        setEmailQueueTotal(data.total || 0);
        // Auto-select first item if none selected and items exist
        if (emails.length > 0 && !selectedEmail) {
          setSelectedEmail(emails[0]);
        }
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
        const items = data.items || [];
        setSmsQueue(items);
        setSmsQueueTotal(data.total || 0);
        // Auto-select first item if none selected and items exist
        if (items.length > 0 && !selectedSms) {
          setSelectedSms(items[0]);
        }
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
  const handleSelectEmail = (email) => {
    setSelectedEmail(email);
    setSelectedSms(null);
  };

  const handleSelectSms = (sms) => {
    setSelectedSms(sms);
    setSelectedEmail(null);
  };

  const handleProcessEmail = async () => {
    if (!selectedEmail || !selectedDisposition) return;

    setProcessingId(selectedEmail.id);
    try {
      let url = `${API_BASE_URL}/api/v1/email-intelligence/queue/${selectedEmail.id}/process-with-intelligence?disposition=${selectedDisposition}`;
      if (createTask) {
        url += `&create_task=true&task_title=${encodeURIComponent(taskTitle)}`;
      }
      const response = await fetch(url, { method: 'POST', headers: getAuthHeaders() });
      if (response.ok) {
        setSelectedEmail(null);
        loadData();
        loadStats();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || error.error || 'Failed to process'}`);
      }
    } catch (error) {
      console.error('Error processing:', error);
      alert('Failed to process');
    } finally {
      setProcessingId(null);
    }
  };

  const handleProcessSms = async () => {
    if (!selectedSms || !selectedDisposition) return;

    setProcessingId(selectedSms.id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/queue/${selectedSms.id}/disposition`,
        {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            sms_id: selectedSms.id,
            disposition: selectedDisposition,
            processing_notes: taskTitle || null
          })
        }
      );
      if (response.ok) {
        setSelectedSms(null);
        loadData();
        loadStats();
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail || error.error || 'Failed to process'}`);
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

  // ================== DELETE HANDLERS ==================
  const handleDeleteEmail = async (emailId) => {
    if (!window.confirm('Are you sure you want to delete this email?')) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/email-intelligence/queue/${emailId}`,
        { method: 'DELETE', headers: getAuthHeaders() }
      );
      if (response.ok) {
        if (selectedEmail?.id === emailId) setSelectedEmail(null);
        loadData();
        loadStats();
      } else {
        alert('Failed to delete email');
      }
    } catch (error) {
      console.error('Error deleting email:', error);
      alert('Failed to delete email');
    }
  };

  const handleDeleteSms = async (smsId) => {
    if (!window.confirm('Are you sure you want to delete this SMS?')) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sms-intelligence/queue/${smsId}`,
        { method: 'DELETE', headers: getAuthHeaders() }
      );
      if (response.ok) {
        if (selectedSms?.id === smsId) setSelectedSms(null);
        loadData();
        loadStats();
      } else {
        alert('Failed to delete SMS');
      }
    } catch (error) {
      console.error('Error deleting SMS:', error);
      alert('Failed to delete SMS');
    }
  };

  const toggleEmailSelection = (emailId, e) => {
    e.stopPropagation();
    setSelectedEmailIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(emailId)) {
        newSet.delete(emailId);
      } else {
        newSet.add(emailId);
      }
      return newSet;
    });
  };

  const toggleSmsSelection = (smsId, e) => {
    e.stopPropagation();
    setSelectedSmsIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(smsId)) {
        newSet.delete(smsId);
      } else {
        newSet.add(smsId);
      }
      return newSet;
    });
  };

  const handleSelectAllEmails = () => {
    const allSelected = emailQueue.every(e => selectedEmailIds.has(e.id));
    if (allSelected) {
      setSelectedEmailIds(new Set());
    } else {
      setSelectedEmailIds(new Set(emailQueue.map(e => e.id)));
    }
  };

  const handleSelectAllSms = () => {
    const allSelected = smsQueue.every(s => selectedSmsIds.has(s.id));
    if (allSelected) {
      setSelectedSmsIds(new Set());
    } else {
      setSelectedSmsIds(new Set(smsQueue.map(s => s.id)));
    }
  };

  const handleBulkDeleteEmails = async () => {
    if (selectedEmailIds.size === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${selectedEmailIds.size} emails? This cannot be undone.`)) return;

    setBulkDeleting(true);
    let successCount = 0;

    for (const emailId of selectedEmailIds) {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/email-intelligence/queue/${emailId}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
        if (response.ok) successCount++;
      } catch (error) {
        console.error(`Failed to delete email ${emailId}:`, error);
      }
    }

    setSelectedEmailIds(new Set());
    setSelectedEmail(null);
    setBulkDeleting(false);
    loadData();
    loadStats();

    if (successCount < selectedEmailIds.size) {
      alert(`Deleted ${successCount} emails. Some failed.`);
    }
  };

  const handleBulkDeleteSms = async () => {
    if (selectedSmsIds.size === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${selectedSmsIds.size} SMS messages? This cannot be undone.`)) return;

    setBulkDeleting(true);
    let successCount = 0;

    for (const smsId of selectedSmsIds) {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/sms-intelligence/queue/${smsId}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
        if (response.ok) successCount++;
      } catch (error) {
        console.error(`Failed to delete SMS ${smsId}:`, error);
      }
    }

    setSelectedSmsIds(new Set());
    setSelectedSms(null);
    setBulkDeleting(false);
    loadData();
    loadStats();

    if (successCount < selectedSmsIds.size) {
      alert(`Deleted ${successCount} SMS messages. Some failed.`);
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

  const formatFullDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
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
    const digits = phone.replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('1')) {
      return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
    }
    if (digits.length === 10) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    }
    return phone;
  };

  const getMatchConfidence = (item) => {
    if (item.matched_loan_id || item.matched_lead_id) {
      return item.match_confidence || 85;
    }
    return 0;
  };

  // ================== RENDER DETAIL PANEL ==================
  const renderEmailDetailPanel = () => {
    if (!selectedEmail) return null;

    const matchConfidence = getMatchConfidence(selectedEmail);
    const hasLowConfidence = matchConfidence < 70;

    return (
      <div className="detail-panel">
        <div className="detail-panel-header">
          <div className="detail-source-badge">
            {selectedEmail.ai_analysis?.disposition?.toUpperCase().replace(/_/g, ' ') || 'EMAIL'}
          </div>
          <button className="detail-close-btn" onClick={() => setSelectedEmail(null)}>×</button>
        </div>

        <h2 className="detail-title">{selectedEmail.ai_analysis?.disposition?.replace(/_/g, ' ') || 'Email'}</h2>

        <div className="detail-info-grid">
          <div className="detail-info-item">
            <span className="detail-info-label">FROM</span>
            <span className="detail-info-value">{selectedEmail.from_name || selectedEmail.from_email}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">SUBJECT</span>
            <span className="detail-info-value">{selectedEmail.subject || '(No Subject)'}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">PRIORITY</span>
            <span className={`priority-badge ${getUrgencyLabel(selectedEmail.ai_analysis?.urgency_level || 2).label.toLowerCase()}`}>
              {getUrgencyLabel(selectedEmail.ai_analysis?.urgency_level || 2).label.toUpperCase()}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">SOURCE</span>
            <span className="detail-info-value">Email Intelligence</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">OWNER</span>
            <span className="detail-info-value">Loan Officer</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">DATE RECEIVED</span>
            <span className="detail-info-value">{formatFullDate(selectedEmail.sent_date)}</span>
          </div>
        </div>

        {/* Flagged for Review Banner */}
        {hasLowConfidence && (
          <div className="flagged-banner">
            <span className="flag-icon">⚠</span>
            <div className="flag-content">
              <span className="flag-title">Flagged for Review:</span>
              <span className="flag-reason">Low match confidence</span>
            </div>
            <span className="flag-confidence">Match Confidence: {matchConfidence}%</span>
          </div>
        )}

        {/* Where should this data go? */}
        <div className="entity-routing-section">
          <h4>Where should this data go?</h4>
          <div className="entity-options">
            <div className={`entity-option ${selectedEmail.matched_loan_id ? 'has-match' : ''}`}>
              <span className="entity-icon">📁</span>
              <span className="entity-label">Active Loan</span>
              <span className="entity-status">
                {selectedEmail.matched_loan_id ? `Loan #${selectedEmail.matched_loan_id}` : 'No match found'}
              </span>
            </div>
            <div className={`entity-option ${selectedEmail.matched_lead_id ? 'has-match' : ''}`}>
              <span className="entity-icon">👤</span>
              <span className="entity-label">Lead</span>
              <span className="entity-status">
                {selectedEmail.matched_lead_id ? `Lead #${selectedEmail.matched_lead_id}` : 'No match found'}
              </span>
            </div>
            <div className="entity-option create-new">
              <span className="entity-icon">+</span>
              <span className="entity-label">Create New Loan</span>
              <span className="entity-status">{selectedEmail.from_name || selectedEmail.from_email}</span>
            </div>
          </div>
        </div>

        {/* Matched Entity */}
        <div className="matched-entity-section">
          <h4>Matched Entity</h4>
          <div className="confidence-indicator">
            <span className={`confidence-bar ${matchConfidence >= 70 ? 'high' : matchConfidence >= 40 ? 'medium' : 'low'}`}>
              <span className="confidence-fill" style={{ width: `${matchConfidence}%` }}></span>
            </span>
            <span className="confidence-text">Match Confidence: {matchConfidence}%</span>
          </div>
        </div>

        {/* Extracted Fields */}
        <div className="extracted-fields-section">
          <h4>EXTRACTED FIELDS</h4>
          <div className="extracted-fields-grid">
            <div className="extracted-field">
              <span className="field-label">FROM NAME</span>
              <span className="field-confidence">95%</span>
              <span className="field-value">{selectedEmail.from_name || '-'}</span>
            </div>
            <div className="extracted-field">
              <span className="field-label">FROM EMAIL</span>
              <span className="field-confidence">100%</span>
              <span className="field-value">{selectedEmail.from_email || '-'}</span>
            </div>
            <div className="extracted-field">
              <span className="field-label">SUBJECT</span>
              <span className="field-confidence">100%</span>
              <span className="field-value">{selectedEmail.subject || '-'}</span>
            </div>
            {selectedEmail.has_attachments && (
              <div className="extracted-field">
                <span className="field-label">ATTACHMENTS</span>
                <span className="field-confidence">100%</span>
                <span className="field-value">{selectedEmail.attachment_count} file(s)</span>
              </div>
            )}
          </div>
        </div>

        {/* AI Analysis */}
        {selectedEmail.ai_analysis && (
          <div className="ai-analysis-section">
            <h4>AI ANALYSIS</h4>
            <div className="analysis-grid">
              <div className="analysis-item">
                <span className="analysis-label">Summary</span>
                <span className="analysis-value">{selectedEmail.ai_analysis.summary || '-'}</span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Disposition</span>
                <span className="analysis-value">{selectedEmail.ai_analysis.disposition?.replace(/_/g, ' ') || '-'}</span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Sentiment</span>
                <span className="analysis-value sentiment" style={{ color: getSentimentColor(selectedEmail.ai_analysis.sentiment) }}>
                  {selectedEmail.ai_analysis.sentiment || '-'}
                </span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Urgency</span>
                <span className="analysis-value">{selectedEmail.ai_analysis.urgency_level || 0}/5</span>
              </div>
            </div>
          </div>
        )}

        {/* Message Preview */}
        <div className="message-preview-section">
          <h4>MESSAGE PREVIEW</h4>
          <div className="message-content">
            {selectedEmail.body_preview || selectedEmail.body_full || 'No content'}
          </div>
        </div>

        {/* Disposition Selection */}
        {selectedEmail.status === 'pending' && (
          <div className="disposition-section">
            <h4>SET DISPOSITION</h4>
            <div className="disposition-grid">
              {emailDispositionOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`disposition-option ${selectedDisposition === opt.value ? 'selected' : ''}`}
                  onClick={() => setSelectedDisposition(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="task-option">
              <label>
                <input type="checkbox" checked={createTask} onChange={(e) => setCreateTask(e.target.checked)} />
                Create follow-up task
              </label>
              {createTask && (
                <input
                  type="text"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="Task title"
                  className="task-title-input"
                />
              )}
            </div>

            <div className="detail-actions">
              <button
                className="process-btn"
                onClick={handleProcessEmail}
                disabled={!selectedDisposition || processingId === selectedEmail.id}
              >
                {processingId === selectedEmail.id ? 'Processing...' : 'Process Email'}
              </button>
              <button className="skip-btn" onClick={() => setSelectedEmail(null)}>
                Skip
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderSmsDetailPanel = () => {
    if (!selectedSms) return null;

    const matchConfidence = getMatchConfidence(selectedSms);
    const hasLowConfidence = matchConfidence < 70;

    return (
      <div className="detail-panel">
        <div className="detail-panel-header">
          <div className="detail-source-badge">
            {selectedSms.ai_analysis?.disposition?.toUpperCase().replace(/_/g, ' ') || 'SMS'}
          </div>
          <button className="detail-close-btn" onClick={() => setSelectedSms(null)}>×</button>
        </div>

        <h2 className="detail-title">{selectedSms.ai_analysis?.intent?.replace(/_/g, ' ') || 'SMS Message'}</h2>

        <div className="detail-info-grid">
          <div className="detail-info-item">
            <span className="detail-info-label">FROM</span>
            <span className="detail-info-value">{formatPhone(selectedSms.from_phone)}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">TO</span>
            <span className="detail-info-value">{formatPhone(selectedSms.to_phone)}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">DIRECTION</span>
            <span className={`direction-badge ${selectedSms.direction}`}>
              {selectedSms.direction?.toUpperCase()}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">SOURCE</span>
            <span className="detail-info-value">SMS Intelligence</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">OWNER</span>
            <span className="detail-info-value">Loan Officer</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">DATE RECEIVED</span>
            <span className="detail-info-value">{formatFullDate(selectedSms.sent_at || selectedSms.received_at)}</span>
          </div>
        </div>

        {/* Flagged for Review Banner */}
        {hasLowConfidence && (
          <div className="flagged-banner">
            <span className="flag-icon">⚠</span>
            <div className="flag-content">
              <span className="flag-title">Flagged for Review:</span>
              <span className="flag-reason">Low match confidence</span>
            </div>
            <span className="flag-confidence">Match Confidence: {matchConfidence}%</span>
          </div>
        )}

        {/* Where should this data go? */}
        <div className="entity-routing-section">
          <h4>Where should this data go?</h4>
          <div className="entity-options">
            <div className={`entity-option ${selectedSms.matched_loan_id ? 'has-match' : ''}`}>
              <span className="entity-icon">📁</span>
              <span className="entity-label">Active Loan</span>
              <span className="entity-status">
                {selectedSms.matched_loan_id ? `Loan #${selectedSms.matched_loan_id}` : 'No match found'}
              </span>
            </div>
            <div className={`entity-option ${selectedSms.matched_lead_id ? 'has-match' : ''}`}>
              <span className="entity-icon">👤</span>
              <span className="entity-label">Lead</span>
              <span className="entity-status">
                {selectedSms.matched_lead_id ? `Lead #${selectedSms.matched_lead_id}` : 'No match found'}
              </span>
            </div>
            <div className="entity-option create-new">
              <span className="entity-icon">+</span>
              <span className="entity-label">Create New Loan</span>
              <span className="entity-status">{formatPhone(selectedSms.from_phone)}</span>
            </div>
          </div>
        </div>

        {/* Matched Entity */}
        <div className="matched-entity-section">
          <h4>Matched Entity</h4>
          <div className="confidence-indicator">
            <span className={`confidence-bar ${matchConfidence >= 70 ? 'high' : matchConfidence >= 40 ? 'medium' : 'low'}`}>
              <span className="confidence-fill" style={{ width: `${matchConfidence}%` }}></span>
            </span>
            <span className="confidence-text">Match Confidence: {matchConfidence}%</span>
          </div>
        </div>

        {/* Extracted Fields */}
        <div className="extracted-fields-section">
          <h4>EXTRACTED FIELDS</h4>
          <div className="extracted-fields-grid">
            <div className="extracted-field">
              <span className="field-label">PHONE NUMBER</span>
              <span className="field-confidence">100%</span>
              <span className="field-value">{formatPhone(selectedSms.from_phone)}</span>
            </div>
            {selectedSms.loan_borrower_name && (
              <div className="extracted-field">
                <span className="field-label">BORROWER NAME</span>
                <span className="field-confidence">90%</span>
                <span className="field-value">{selectedSms.loan_borrower_name}</span>
              </div>
            )}
            {selectedSms.lead_name && (
              <div className="extracted-field">
                <span className="field-label">LEAD NAME</span>
                <span className="field-confidence">90%</span>
                <span className="field-value">{selectedSms.lead_name}</span>
              </div>
            )}
            {selectedSms.has_media && (
              <div className="extracted-field">
                <span className="field-label">MEDIA</span>
                <span className="field-confidence">100%</span>
                <span className="field-value">{selectedSms.media_count} file(s)</span>
              </div>
            )}
          </div>
        </div>

        {/* AI Analysis */}
        {selectedSms.ai_analysis && (
          <div className="ai-analysis-section">
            <h4>AI ANALYSIS</h4>
            <div className="analysis-grid">
              <div className="analysis-item">
                <span className="analysis-label">Intent</span>
                <span className="analysis-value">{selectedSms.ai_analysis.intent || '-'}</span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Disposition</span>
                <span className="analysis-value">{selectedSms.ai_analysis.disposition?.replace(/_/g, ' ') || '-'}</span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Sentiment</span>
                <span className="analysis-value sentiment" style={{ color: getSentimentColor(selectedSms.ai_analysis.sentiment) }}>
                  {selectedSms.ai_analysis.sentiment || '-'}
                </span>
              </div>
              <div className="analysis-item">
                <span className="analysis-label">Urgency</span>
                <span className="analysis-value">{selectedSms.ai_analysis.urgency_level || 0}/5</span>
              </div>
              {selectedSms.ai_analysis.documents_mentioned?.length > 0 && (
                <div className="analysis-item full-width">
                  <span className="analysis-label">Documents Mentioned</span>
                  <span className="analysis-value">{selectedSms.ai_analysis.documents_mentioned.join(', ')}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Message Content */}
        <div className="message-preview-section">
          <h4>MESSAGE CONTENT</h4>
          <div className="message-content sms">
            {selectedSms.message_body}
          </div>
        </div>

        {/* Disposition Selection */}
        {selectedSms.status !== 'completed' && (
          <div className="disposition-section">
            <h4>SET DISPOSITION</h4>
            <div className="disposition-grid">
              {smsDispositionOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`disposition-option ${selectedDisposition === opt.value ? 'selected' : ''}`}
                  onClick={() => setSelectedDisposition(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="detail-actions">
              <button
                className="process-btn"
                onClick={handleProcessSms}
                disabled={!selectedDisposition || processingId === selectedSms.id}
              >
                {processingId === selectedSms.id ? 'Processing...' : 'Process SMS'}
              </button>
              <button className="skip-btn" onClick={() => setSelectedSms(null)}>
                Skip
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ================== RENDER ==================
  const currentStats = commMode === 'email' ? emailStats : smsStats;
  const hasDetailPanel = selectedEmail || selectedSms;

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
          <span className="mode-label">Email</span>
          {emailStats.pending_count > 0 && (
            <span className="mode-badge">{emailStats.pending_count}</span>
          )}
        </button>
        <button
          className={`mode-btn ${commMode === 'sms' ? 'active' : ''}`}
          onClick={() => setCommMode('sms')}
        >
          <span className="mode-label">SMS</span>
          {smsStats.totals?.pending > 0 && (
            <span className="mode-badge">{smsStats.totals.pending}</span>
          )}
        </button>
        <button
          className={`mode-btn ${commMode === 'dialer' ? 'active' : ''}`}
          onClick={() => setCommMode('dialer')}
        >
          <span className="mode-label">Power Dialer</span>
        </button>
      </div>

      {/* Power Dialer Mode */}
      {commMode === 'dialer' && (
        <PowerDialer />
      )}

      {/* Stats Grid - only show for email/sms modes */}
      {commMode !== 'dialer' && (
      <div className="stats-grid">
        {commMode === 'email' ? (
          <>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'pending' }); setActiveTab('queue'); }}>
              <div className="stat-value">{emailStats.pending_count || 0}</div>
              <div className="stat-label">PENDING</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'processed' }); setActiveTab('queue'); }}>
              <div className="stat-value">{emailStats.processed_count || 0}</div>
              <div className="stat-label">PROCESSED</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('conversations')}>
              <div className="stat-value">{emailStats.conversation_logs_created || 0}</div>
              <div className="stat-label">CONVERSATIONS</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('all-documents')}>
              <div className="stat-value">{emailStats.documents_received || 0}</div>
              <div className="stat-label">DOCS RECEIVED</div>
            </div>
          </>
        ) : (
          <>
            <div className="stat-card clickable" onClick={() => { setSmsFilters({ ...smsFilters, status: 'pending' }); setActiveTab('queue'); }}>
              <div className="stat-value">{smsStats.totals?.pending || 0}</div>
              <div className="stat-label">PENDING</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setSmsFilters({ ...smsFilters, requiresResponse: 'yes' }); setActiveTab('queue'); }}>
              <div className="stat-value">{smsStats.totals?.needs_response || 0}</div>
              <div className="stat-label">NEED RESPONSE</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('opt-outs')}>
              <div className="stat-value">{smsStats.totals?.opt_outs || 0}</div>
              <div className="stat-label">OPT-OUTS</div>
            </div>
            <div className="stat-card clickable" onClick={() => setActiveTab('sla')}>
              <div className="stat-value">{smsStats.sla?.breached || 0}</div>
              <div className="stat-label">SLA BREACHED</div>
            </div>
          </>
        )}
      </div>
      )}

      {/* Tabs - only show for email/sms modes */}
      {commMode !== 'dialer' && (
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
      )}

      {/* Split Panel Layout for Queue - only show for email/sms modes */}
      {commMode !== 'dialer' && activeTab === 'queue' && (
        <div className={`split-panel-layout ${hasDetailPanel ? 'has-detail' : ''}`}>
          {/* Left Panel - List */}
          <div className="list-panel">
            <div className="filters-row">
              <div className="filters-left">
                <input
                  type="checkbox"
                  className="select-all-checkbox"
                  checked={commMode === 'email'
                    ? emailQueue.length > 0 && emailQueue.every(e => selectedEmailIds.has(e.id))
                    : smsQueue.length > 0 && smsQueue.every(s => selectedSmsIds.has(s.id))}
                  onChange={commMode === 'email' ? handleSelectAllEmails : handleSelectAllSms}
                  title="Select all"
                />
                {commMode === 'email' ? (
                  <>
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
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
              <div className="filters-right">
                {(commMode === 'email' ? selectedEmailIds.size : selectedSmsIds.size) > 0 && (
                  <button
                    className="bulk-delete-btn"
                    onClick={commMode === 'email' ? handleBulkDeleteEmails : handleBulkDeleteSms}
                    disabled={bulkDeleting}
                  >
                    {bulkDeleting ? 'Deleting...' : `🗑️ Delete (${commMode === 'email' ? selectedEmailIds.size : selectedSmsIds.size})`}
                  </button>
                )}
                <button className="refresh-btn" onClick={loadData}>Refresh</button>
              </div>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : commMode === 'email' ? (
              emailQueue.length === 0 ? (
                <div className="empty-state">
                  <h3>No emails in queue</h3>
                  <p>Sync your email to import messages for processing</p>
                </div>
              ) : (
                <div className="queue-list">
                  {emailQueue.map(email => (
                    <div
                      key={email.id}
                      className={`queue-item ${selectedEmail?.id === email.id ? 'selected' : ''} ${email.status} ${selectedEmailIds.has(email.id) ? 'checked' : ''}`}
                      onClick={() => handleSelectEmail(email)}
                    >
                      <div className="queue-item-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedEmailIds.has(email.id)}
                          onChange={(e) => toggleEmailSelection(email.id, e)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="queue-item-content">
                        <div className="queue-item-header">
                          <span className={`queue-item-type ${email.ai_analysis?.disposition || 'general'}`}>
                            {email.ai_analysis?.disposition?.replace(/_/g, ' ') || 'General'}
                          </span>
                          {(!email.matched_loan_id && !email.matched_lead_id) && (
                            <span className="needs-review-badge">NEEDS REVIEW</span>
                          )}
                        </div>
                        <div className="queue-item-subject">{email.subject || '(No Subject)'}</div>
                        <div className="queue-item-preview">
                          {email.body_preview?.substring(0, 100)}...
                        </div>
                        <div className="queue-item-reason">
                          <span className="reason-label">Reason:</span> {email.ai_analysis?.summary?.substring(0, 60) || 'Pending analysis'}...
                        </div>
                      </div>
                      <button
                        className="queue-item-delete-btn"
                        onClick={(e) => { e.stopPropagation(); handleDeleteEmail(email.id); }}
                        title="Delete email"
                      >
                        🗑️
                      </button>
                    </div>
                  ))}
                </div>
              )
            ) : (
              smsQueue.length === 0 ? (
                <div className="empty-state">
                  <h3>No SMS messages in queue</h3>
                  <p>Messages will appear here when received via Twilio webhook</p>
                </div>
              ) : (
                <div className="queue-list">
                  {smsQueue.map(sms => (
                    <div
                      key={sms.id}
                      className={`queue-item ${selectedSms?.id === sms.id ? 'selected' : ''} ${sms.status} ${selectedSmsIds.has(sms.id) ? 'checked' : ''}`}
                      onClick={() => handleSelectSms(sms)}
                    >
                      <div className="queue-item-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedSmsIds.has(sms.id)}
                          onChange={(e) => toggleSmsSelection(sms.id, e)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="queue-item-content">
                        <div className="queue-item-header">
                          <span className={`queue-item-type ${sms.ai_analysis?.disposition || sms.disposition || 'general'}`}>
                            {(sms.ai_analysis?.disposition || sms.disposition || 'General').replace(/_/g, ' ')}
                          </span>
                          {(!sms.matched_loan_id && !sms.matched_lead_id) && (
                            <span className="needs-review-badge">NEEDS REVIEW</span>
                          )}
                        </div>
                        <div className="queue-item-subject">{formatPhone(sms.from_phone)} ({sms.direction})</div>
                        <div className="queue-item-preview">
                          {sms.message_body?.substring(0, 100)}...
                        </div>
                        <div className="queue-item-reason">
                          <span className="reason-label">Reason:</span> {sms.requires_response ? 'Requires response' : 'Pending review'}
                        </div>
                      </div>
                      <button
                        className="queue-item-delete-btn"
                        onClick={(e) => { e.stopPropagation(); handleDeleteSms(sms.id); }}
                        title="Delete SMS"
                      >
                        🗑️
                      </button>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>

          {/* Right Panel - Detail */}
          {hasDetailPanel && (
            <div className="detail-panel-container">
              {selectedEmail && renderEmailDetailPanel()}
              {selectedSms && renderSmsDetailPanel()}
            </div>
          )}
        </div>
      )}

      {/* Non-queue tabs content - only show for email/sms modes */}
      {commMode !== 'dialer' && activeTab !== 'queue' && (
        <div className="tab-content">
          {/* Email Conversations */}
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
                <button className="refresh-btn" onClick={loadEmailConversations}>Load Conversations</button>
              </div>
              {!selectedLoanId ? (
                <div className="empty-state">
                  <h3>Enter a Loan ID</h3>
                  <p>View the AI-generated conversation log for any loan</p>
                </div>
              ) : loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : emailConversations.length === 0 ? (
                <div className="empty-state">
                  <h3>No conversations found</h3>
                  <p>No conversation logs for Loan #{selectedLoanId}</p>
                </div>
              ) : (
                <div className="conversation-list">
                  {emailConversations.map(conv => (
                    <div key={conv.id} className="conversation-card">
                      <div className="conv-header">
                        <span className="conv-direction">{conv.direction}</span>
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

          {/* Email Documents */}
          {commMode === 'email' && activeTab === 'documents' && (
            <div className="documents-section">
              <div className="filters-row">
                <input type="number" placeholder="Enter Loan ID" value={docLoanId} onChange={(e) => setDocLoanId(e.target.value)} className="loan-id-input" />
                <button className="refresh-btn" onClick={loadEmailDocuments}>Load Documents</button>
              </div>
              {!docLoanId ? (
                <div className="empty-state"><h3>Enter a Loan ID</h3></div>
              ) : loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : emailDocuments.length === 0 ? (
                <div className="empty-state"><h3>No documents tracked</h3></div>
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

          {/* All Email Documents */}
          {commMode === 'email' && activeTab === 'all-documents' && (
            <div className="all-documents-section">
              <div className="section-header">
                <h3>All Received Documents</h3>
                <button className="refresh-btn" onClick={loadAllEmailDocuments}>Refresh</button>
              </div>
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : emailAllDocuments.length === 0 ? (
                <div className="empty-state"><h3>No documents tracked</h3></div>
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

          {/* Email SLA */}
          {commMode === 'email' && activeTab === 'sla' && (
            <div className="sla-section">
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : emailSlaItems.length === 0 ? (
                <div className="empty-state"><h3>All caught up!</h3><p>No pending SLA items</p></div>
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

          {/* SMS Conversations */}
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
                <button className="refresh-btn" onClick={loadSmsConversations}>Load Conversations</button>
              </div>
              {!smsPhoneFilter ? (
                <div className="empty-state">
                  <h3>Enter a Phone Number</h3>
                  <p>View the SMS conversation history for any phone number</p>
                </div>
              ) : loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : smsConversations.length === 0 ? (
                <div className="empty-state">
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

          {/* SMS Templates */}
          {commMode === 'sms' && activeTab === 'templates' && (
            <div className="templates-section">
              <div className="section-header">
                <h3>SMS Templates</h3>
                <button className="refresh-btn" onClick={loadSmsTemplates}>Refresh</button>
              </div>
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : smsTemplates.length === 0 ? (
                <div className="empty-state">
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

          {/* SMS Opt-Outs */}
          {commMode === 'sms' && activeTab === 'opt-outs' && (
            <div className="opt-outs-section">
              <div className="section-header">
                <h3>Opted-Out Phone Numbers</h3>
                <button className="refresh-btn" onClick={loadSmsOptOuts}>Refresh</button>
              </div>
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : smsOptOuts.length === 0 ? (
                <div className="empty-state">
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

          {/* SMS SLA */}
          {commMode === 'sms' && activeTab === 'sla' && (
            <div className="sla-section">
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : smsSlaItems.length === 0 ? (
                <div className="empty-state">
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

          {/* SMS Doc Mentions */}
          {commMode === 'sms' && activeTab === 'doc-mentions' && (
            <div className="doc-mentions-section">
              <div className="section-header">
                <h3>Document Mentions in SMS</h3>
                <button className="refresh-btn" onClick={loadSmsDocMentions}>Refresh</button>
              </div>
              {loading ? (
                <div className="loading-spinner">Loading...</div>
              ) : smsDocMentions.length === 0 ? (
                <div className="empty-state">
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
      )}
    </div>
  );
}

export default CommunicationIntelligence;
