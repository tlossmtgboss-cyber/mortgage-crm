import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import PowerDialer from './PowerDialer';
import { useLayoutFix } from '../hooks/useLayoutFix';
import { getAuthHeaders } from '../utils/auth';
import './CommunicationIntelligence.css';
import { toast } from '../utils/toast';

function CommunicationIntelligence() {
  const navigate = useNavigate();

  // Communication mode: 'email' or 'sms'
  const [commMode, setCommMode] = useState('email');

  // Subtabs within each mode
  const [activeTab, setActiveTab] = useState('queue');
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState(null);

  // ================== EMAIL/AI CONVERSATIONS STATE ==================
  const [aiConversations, setAiConversations] = useState([]);
  const [aiConversationsTotal, setAiConversationsTotal] = useState(0);
  const [emailFilters, setEmailFilters] = useState({
    status: '',  // all, active, closed
  });
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [emailStats, setEmailStats] = useState({});

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
  const [selectedConversationIds, setSelectedConversationIds] = useState(new Set());
  const [selectedSmsIds, setSelectedSmsIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // ================== LAYOUT FIX ==================
  const { containerRef, triggerRecalculation } = useLayoutFix([loading, aiConversations, smsQueue]);

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

  // Reset tab when switching modes
  useEffect(() => {
    setActiveTab('queue');
    setSelectedConversation(null);
    setConversationMessages([]);
    setSelectedSms(null);
  }, [commMode]);

  // Load data when mode or tab changes
  useEffect(() => {
    loadData();
    loadStats();
  }, [commMode, activeTab, emailFilters, smsFilters]);

  // Load conversation messages when conversation is selected
  useEffect(() => {
    if (selectedConversation) {
      loadConversationMessages(selectedConversation.conversation_id);
    } else {
      setConversationMessages([]);
    }
  }, [selectedConversation]);

  // Update disposition when selection changes
  useEffect(() => {
    if (selectedConversation) {
      setSelectedDisposition(selectedConversation.conversation_type || 'general');
      setTaskTitle(`Follow up: Conversation with ${selectedConversation.recipient_name || selectedConversation.recipient_email}`);
    } else if (selectedSms) {
      setSelectedDisposition(selectedSms.ai_analysis?.disposition || selectedSms.disposition || 'general_correspondence');
      setTaskTitle(`Follow up: SMS from ${selectedSms.from_phone}`);
    }
    setCreateTask(false);
  }, [selectedConversation, selectedSms]);

  const loadStats = async () => {
    try {
      if (commMode === 'email') {
        // Count AI conversations for stats
        const [activeRes, closedRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/ai-email/conversations?status=active`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE_URL}/api/v1/ai-email/conversations?status=closed`, { headers: getAuthHeaders() })
        ]);
        const activeData = activeRes.ok ? await activeRes.json() : [];
        const closedData = closedRes.ok ? await closedRes.json() : [];
        setEmailStats({
          active_conversations: activeData.length || 0,
          closed_conversations: closedData.length || 0,
          total_conversations: (activeData.length || 0) + (closedData.length || 0)
        });
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
        // Email mode now only shows AI conversations
        await loadAiConversations();
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

  // ================== AI CONVERSATION LOADERS ==================
  const loadAiConversations = async () => {
    try {
      let url = `${API_BASE_URL}/api/v1/ai-email/conversations?limit=50`;
      if (emailFilters.status) url += `&status=${emailFilters.status}`;

      const response = await fetch(url, { headers: getAuthHeaders() });
      if (response.ok) {
        const data = await response.json();
        const conversations = data || [];
        setAiConversations(conversations);
        setAiConversationsTotal(conversations.length);
        // Auto-select first item if none selected and items exist
        if (conversations.length > 0 && !selectedConversation) {
          setSelectedConversation(conversations[0]);
        }
      }
    } catch (error) {
      console.error('Error loading AI conversations:', error);
    }
  };

  const loadConversationMessages = async (conversationId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai-email/conversations/${conversationId}/messages`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setConversationMessages(data || []);
      }
    } catch (error) {
      console.error('Error loading conversation messages:', error);
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
  const handleSelectConversation = (conversation) => {
    setSelectedConversation(conversation);
    setSelectedSms(null);
  };

  const handleSelectSms = (sms) => {
    setSelectedSms(sms);
    setSelectedConversation(null);
  };

  const handleCloseConversation = async () => {
    if (!selectedConversation) return;

    setProcessingId(selectedConversation.id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai-email/conversations/${selectedConversation.conversation_id}/close`,
        { method: 'PATCH', headers: getAuthHeaders() }
      );
      if (response.ok) {
        loadData();
        loadStats();
      } else {
        const error = await response.json();
        toast.error(`Error: ${error.detail || error.error || 'Failed to close conversation'}`);
      }
    } catch (error) {
      console.error('Error closing conversation:', error);
      toast.error('Failed to close conversation');
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
        toast.error(`Error: ${error.detail || error.error || 'Failed to process'}`);
      }
    } catch (error) {
      console.error('Error processing:', error);
      toast.error('Failed to process');
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
  const handleDeleteConversation = async (conversationId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai-email/conversations/${conversationId}`,
        { method: 'DELETE', headers: getAuthHeaders() }
      );
      if (response.ok) {
        if (selectedConversation?.conversation_id === conversationId) {
          setSelectedConversation(null);
          setConversationMessages([]);
        }
        loadData();
        loadStats();
      } else {
        toast.error('Failed to delete conversation');
      }
    } catch (error) {
      console.error('Error deleting conversation:', error);
      toast.error('Failed to delete conversation');
    }
  };

  const handleDeleteSms = async (smsId) => {
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
        toast.error('Failed to delete SMS');
      }
    } catch (error) {
      console.error('Error deleting SMS:', error);
      toast.error('Failed to delete SMS');
    }
  };

  const toggleConversationSelection = (conversationId, e) => {
    e.stopPropagation();
    setSelectedConversationIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(conversationId)) {
        newSet.delete(conversationId);
      } else {
        newSet.add(conversationId);
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

  const handleSelectAllConversations = () => {
    const allSelected = aiConversations.every(c => selectedConversationIds.has(c.conversation_id));
    if (allSelected) {
      setSelectedConversationIds(new Set());
    } else {
      setSelectedConversationIds(new Set(aiConversations.map(c => c.conversation_id)));
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

  const handleBulkDeleteConversations = async () => {
    if (selectedConversationIds.size === 0) return;

    setBulkDeleting(true);
    let successCount = 0;

    for (const conversationId of selectedConversationIds) {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/ai-email/conversations/${conversationId}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
        if (response.ok) successCount++;
      } catch (error) {
        console.error(`Failed to delete conversation ${conversationId}:`, error);
      }
    }

    setSelectedConversationIds(new Set());
    setSelectedConversation(null);
    setConversationMessages([]);
    setBulkDeleting(false);
    loadData();
    loadStats();

    if (successCount < selectedConversationIds.size) {
      toast.success(`Deleted ${successCount} conversations. Some failed.`);
    }
  };

  const handleBulkDeleteSms = async () => {
    if (selectedSmsIds.size === 0) return;

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
      toast.success(`Deleted ${successCount} SMS messages. Some failed.`);
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
  const renderConversationDetailPanel = () => {
    if (!selectedConversation) return null;

    return (
      <div className="detail-panel">
        <div className="detail-panel-header">
          <div className={`detail-source-badge ${selectedConversation.status}`}>
            {selectedConversation.status?.toUpperCase() || 'ACTIVE'}
          </div>
          <button className="detail-close-btn" onClick={() => { setSelectedConversation(null); setConversationMessages([]); }}>×</button>
        </div>

        <h2 className="detail-title">
          Conversation with {selectedConversation.recipient_name || selectedConversation.recipient_email}
        </h2>

        <div className="detail-info-grid">
          <div className="detail-info-item">
            <span className="detail-info-label">RECIPIENT</span>
            <span className="detail-info-value">{selectedConversation.recipient_name || '-'}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">EMAIL</span>
            <span className="detail-info-value">{selectedConversation.recipient_email}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">TYPE</span>
            <span className="detail-info-value">{selectedConversation.conversation_type?.replace(/_/g, ' ') || 'General'}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">MESSAGES</span>
            <span className="detail-info-value">{selectedConversation.message_count || 0}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">STATUS</span>
            <span className={`status-badge ${selectedConversation.status}`}>
              {selectedConversation.status?.toUpperCase() || 'ACTIVE'}
            </span>
          </div>
          <div className="detail-info-item">
            <span className="detail-info-label">STARTED</span>
            <span className="detail-info-value">{formatFullDate(selectedConversation.created_at)}</span>
          </div>
          {selectedConversation.last_message_at && (
            <div className="detail-info-item">
              <span className="detail-info-label">LAST MESSAGE</span>
              <span className="detail-info-value">{formatFullDate(selectedConversation.last_message_at)}</span>
            </div>
          )}
          {selectedConversation.loan_id && (
            <div className="detail-info-item">
              <span className="detail-info-label">LINKED LOAN</span>
              <span className="detail-info-value">Loan #{selectedConversation.loan_id}</span>
            </div>
          )}
          {selectedConversation.lead_id && (
            <div className="detail-info-item">
              <span className="detail-info-label">LINKED LEAD</span>
              <span className="detail-info-value">Lead #{selectedConversation.lead_id}</span>
            </div>
          )}
        </div>

        {/* Conversation Messages */}
        <div className="conversation-messages-section">
          <h4>CONVERSATION THREAD</h4>
          <div className="conversation-messages">
            {conversationMessages.length === 0 ? (
              <div className="no-messages">Loading messages...</div>
            ) : (
              conversationMessages.map((msg, idx) => (
                <div key={msg.id || idx} className={`conversation-message ${msg.direction}`}>
                  <div className="message-header">
                    <span className="message-sender">
                      {msg.direction === 'outbound' ? 'AI Assistant' : selectedConversation.recipient_name || 'Recipient'}
                    </span>
                    <span className="message-time">{formatFullDate(msg.created_at)}</span>
                    {msg.ai_generated && <span className="ai-badge">AI</span>}
                  </div>
                  <div className="message-subject">{msg.subject}</div>
                  <div className="message-body">{msg.body_text || 'No content'}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="detail-actions">
          {selectedConversation.status === 'active' && (
            <button
              className="process-btn warning"
              onClick={handleCloseConversation}
              disabled={processingId === selectedConversation.id}
            >
              {processingId === selectedConversation.id ? 'Closing...' : 'Close Conversation'}
            </button>
          )}
          <button
            className="delete-btn"
            onClick={() => handleDeleteConversation(selectedConversation.conversation_id)}
          >
            Delete Conversation
          </button>
        </div>
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
  const hasDetailPanel = selectedConversation || selectedSms;

  return (
    <div className="communication-intelligence-page" ref={containerRef}>
      {/* Page Header */}
      <div className="page-header">
        <h1>Communication Intelligence</h1>
        <p className="subtitle">AI-powered two-way conversations with borrowers and clients</p>
      </div>

      {/* Mode Selector */}
      <div className="mode-selector">
        <button
          className={`mode-btn ${commMode === 'email' ? 'active' : ''}`}
          onClick={() => setCommMode('email')}
        >
          <span className="mode-label">Email</span>
          {emailStats.active_conversations > 0 && (
            <span className="mode-badge">{emailStats.active_conversations}</span>
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
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: '' }); }}>
              <div className="stat-value">{emailStats.total_conversations || 0}</div>
              <div className="stat-label">TOTAL</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'active' }); }}>
              <div className="stat-value">{emailStats.active_conversations || 0}</div>
              <div className="stat-label">ACTIVE</div>
            </div>
            <div className="stat-card clickable" onClick={() => { setEmailFilters({ ...emailFilters, status: 'closed' }); }}>
              <div className="stat-value">{emailStats.closed_conversations || 0}</div>
              <div className="stat-label">CLOSED</div>
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

      {/* Tabs - only show for sms mode (email mode doesn't need tabs, just shows conversations) */}
      {commMode === 'sms' && (
      <div className="tabs-container">
        {commMode === 'sms' && (
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

      {/* Split Panel Layout - for email AI conversations and SMS queue */}
      {commMode === 'email' && (
        <div className={`split-panel-layout ${hasDetailPanel ? 'has-detail' : ''}`}>
          {/* Left Panel - AI Conversations List */}
          <div className="list-panel">
            <div className="filters-row">
              <div className="filters-left">
                <input
                  type="checkbox"
                  className="select-all-checkbox"
                  checked={aiConversations.length > 0 && aiConversations.every(c => selectedConversationIds.has(c.conversation_id))}
                  onChange={handleSelectAllConversations}
                  title="Select all"
                />
                <select value={emailFilters.status} onChange={(e) => setEmailFilters({ ...emailFilters, status: e.target.value })}>
                  <option value="">All Status</option>
                  <option value="active">Active</option>
                  <option value="closed">Closed</option>
                </select>
              </div>
              <div className="filters-right">
                {selectedConversationIds.size > 0 && (
                  <button
                    className="bulk-delete-btn"
                    onClick={handleBulkDeleteConversations}
                    disabled={bulkDeleting}
                  >
                    {bulkDeleting ? 'Deleting...' : `Delete (${selectedConversationIds.size})`}
                  </button>
                )}
                <button className="refresh-btn" onClick={loadData}>Refresh</button>
              </div>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : aiConversations.length === 0 ? (
              <div className="empty-state">
                <h3>No AI conversations</h3>
                <p>Start a two-way AI conversation from a loan or lead to see it here</p>
              </div>
            ) : (
              <div className="queue-list">
                {aiConversations.map(conv => (
                  <div
                    key={conv.conversation_id}
                    className={`queue-item ${selectedConversation?.conversation_id === conv.conversation_id ? 'selected' : ''} ${conv.status} ${selectedConversationIds.has(conv.conversation_id) ? 'checked' : ''}`}
                    onClick={() => handleSelectConversation(conv)}
                  >
                    <div className="queue-item-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedConversationIds.has(conv.conversation_id)}
                        onChange={(e) => toggleConversationSelection(conv.conversation_id, e)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    <div className="queue-item-content">
                      <div className="queue-item-header">
                        <span className={`queue-item-type ${conv.conversation_type || 'general'}`}>
                          {conv.conversation_type?.replace(/_/g, ' ') || 'General'}
                        </span>
                        <span className={`status-badge ${conv.status}`}>
                          {conv.status?.toUpperCase() || 'ACTIVE'}
                        </span>
                      </div>
                      <div className="queue-item-subject">{conv.recipient_name || conv.recipient_email}</div>
                      <div className="queue-item-preview">
                        {conv.message_count || 0} messages
                        {conv.last_message_at && ` • Last: ${formatDate(conv.last_message_at)}`}
                      </div>
                    </div>
                    <button
                      className="queue-item-delete-btn"
                      onClick={(e) => { e.stopPropagation(); handleDeleteConversation(conv.conversation_id); }}
                      title="Delete conversation"
                    >
                      🗑️
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel - Detail */}
          {hasDetailPanel && (
            <div className="detail-panel-container">
              {selectedConversation && renderConversationDetailPanel()}
            </div>
          )}
        </div>
      )}

      {/* Split Panel Layout for SMS Queue */}
      {commMode === 'sms' && activeTab === 'queue' && (
        <div className={`split-panel-layout ${hasDetailPanel ? 'has-detail' : ''}`}>
          {/* Left Panel - List */}
          <div className="list-panel">
            <div className="filters-row">
              <div className="filters-left">
                <input
                  type="checkbox"
                  className="select-all-checkbox"
                  checked={smsQueue.length > 0 && smsQueue.every(s => selectedSmsIds.has(s.id))}
                  onChange={handleSelectAllSms}
                  title="Select all"
                />
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
              </div>
              <div className="filters-right">
                {selectedSmsIds.size > 0 && (
                  <button
                    className="bulk-delete-btn"
                    onClick={handleBulkDeleteSms}
                    disabled={bulkDeleting}
                  >
                    {bulkDeleting ? 'Deleting...' : `Delete (${selectedSmsIds.size})`}
                  </button>
                )}
                <button className="refresh-btn" onClick={loadData}>Refresh</button>
              </div>
            </div>

            {loading ? (
              <div className="loading-spinner">Loading...</div>
            ) : smsQueue.length === 0 ? (
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
            )}
          </div>

          {/* Right Panel - Detail */}
          {hasDetailPanel && (
            <div className="detail-panel-container">
              {selectedSms && renderSmsDetailPanel()}
            </div>
          )}
        </div>
      )}

      {/* Non-queue tabs content - only show for sms mode */}
      {commMode === 'sms' && activeTab !== 'queue' && (
        <div className="tab-content">
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
