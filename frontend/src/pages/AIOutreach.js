import React, { useState, useEffect, useCallback } from 'react';
import './AIOutreach.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const AIOutreach = () => {
  const [activeTab, setActiveTab] = useState('send'); // send, conversations, stats
  const [contacts, setContacts] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [message, setMessage] = useState(null);

  // Form state
  const [selectedContact, setSelectedContact] = useState(null);
  const [channel, setChannel] = useState('email');
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [customMessage, setCustomMessage] = useState('');
  const [customSubject, setCustomSubject] = useState('');
  const [manualEmail, setManualEmail] = useState('');
  const [manualPhone, setManualPhone] = useState('');
  const [manualName, setManualName] = useState('');

  // Conversation detail
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [conversationDetail, setConversationDetail] = useState(null);

  const getAuthHeaders = () => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json'
  });

  const fetchContacts = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (searchTerm) params.append('search', searchTerm);

      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/contacts?${params}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setContacts(data.contacts || []);
      }
    } catch (err) {
      console.error('Error fetching contacts:', err);
    }
  }, [searchTerm]);

  const fetchTemplates = useCallback(async () => {
    try {
      const params = channel ? `?channel=${channel}` : '';
      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/templates${params}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      }
    } catch (err) {
      console.error('Error fetching templates:', err);
    }
  }, [channel]);

  const fetchConversations = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/conversations?limit=50`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setConversations(data.conversations || []);
      }
    } catch (err) {
      console.error('Error fetching conversations:', err);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/stats?days=30`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  }, []);

  const fetchConversationDetail = async (convId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/conversations/${convId}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setConversationDetail(data);
      }
    } catch (err) {
      console.error('Error fetching conversation detail:', err);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchContacts(), fetchTemplates(), fetchConversations(), fetchStats()]);
      setLoading(false);
    };
    loadData();
  }, [fetchContacts, fetchTemplates, fetchConversations, fetchStats]);

  useEffect(() => {
    fetchTemplates();
  }, [channel, fetchTemplates]);

  useEffect(() => {
    const delaySearch = setTimeout(() => {
      fetchContacts();
    }, 300);
    return () => clearTimeout(delaySearch);
  }, [searchTerm, fetchContacts]);

  const handleSendOutreach = async () => {
    // Validate
    if (channel === 'email' && !selectedContact?.email && !manualEmail) {
      setMessage({ type: 'error', text: 'Please select a contact with email or enter an email address' });
      return;
    }
    if (channel === 'sms' && !selectedContact?.phone && !manualPhone) {
      setMessage({ type: 'error', text: 'Please select a contact with phone or enter a phone number' });
      return;
    }
    if (!selectedTemplate && !customMessage) {
      setMessage({ type: 'error', text: 'Please select a template or enter a custom message' });
      return;
    }

    setSending(true);
    setMessage(null);

    try {
      const payload = {
        channel: channel,
        template_id: selectedTemplate?.id || null,
        custom_message: customMessage || null
      };

      if (selectedContact) {
        payload.contact_id = selectedContact.id;
        payload.email = selectedContact.email;
        payload.phone = selectedContact.phone;
        payload.first_name = selectedContact.name?.split(' ')[0] || 'there';
      } else {
        payload.email = manualEmail;
        payload.phone = manualPhone;
        payload.first_name = manualName || 'there';
      }

      const response = await fetch(`${API_BASE}/api/v1/ai-outreach/start`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setMessage({ type: 'success', text: data.message || 'Outreach sent successfully!' });
        // Reset form
        setSelectedContact(null);
        setSelectedTemplate(null);
        setCustomMessage('');
        setManualEmail('');
        setManualPhone('');
        setManualName('');
        // Refresh conversations
        fetchConversations();
        fetchStats();
      } else {
        setMessage({ type: 'error', text: data.detail || data.message || 'Failed to send outreach' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error sending outreach: ' + err.message });
    } finally {
      setSending(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleString();
  };

  if (loading) {
    return <div className="ai-outreach loading">Loading...</div>;
  }

  return (
    <div className="ai-outreach">
      <div className="outreach-header">
        <h1>AI Outreach</h1>
        <p>Send AI-powered emails and SMS to leads. Sarah will handle all replies automatically.</p>
      </div>

      {message && (
        <div className={`message-alert ${message.type}`}>
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="outreach-tabs">
        <button
          className={`tab-btn ${activeTab === 'send' ? 'active' : ''}`}
          onClick={() => setActiveTab('send')}
        >
          Send Outreach
        </button>
        <button
          className={`tab-btn ${activeTab === 'conversations' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversations')}
        >
          Conversations ({conversations.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'stats' ? 'active' : ''}`}
          onClick={() => setActiveTab('stats')}
        >
          Statistics
        </button>
      </div>

      {/* Send Outreach Tab */}
      {activeTab === 'send' && (
        <div className="send-outreach-container">
          <div className="outreach-form">
            {/* Channel Selection */}
            <div className="form-section">
              <h3>1. Select Channel</h3>
              <div className="channel-buttons">
                <button
                  className={`channel-btn ${channel === 'email' ? 'active' : ''}`}
                  onClick={() => setChannel('email')}
                >
                  <span className="channel-icon">📧</span>
                  Email
                </button>
                <button
                  className={`channel-btn ${channel === 'sms' ? 'active' : ''}`}
                  onClick={() => setChannel('sms')}
                >
                  <span className="channel-icon">💬</span>
                  SMS
                </button>
              </div>
            </div>

            {/* Contact Selection */}
            <div className="form-section">
              <h3>2. Select Recipient</h3>
              <div className="contact-search">
                <input
                  type="text"
                  placeholder="Search contacts by name, email, or phone..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>

              <div className="contact-list">
                {contacts.length === 0 ? (
                  <div className="no-contacts">No contacts found</div>
                ) : (
                  contacts.slice(0, 10).map(contact => (
                    <div
                      key={contact.id}
                      className={`contact-item ${selectedContact?.id === contact.id ? 'selected' : ''}`}
                      onClick={() => setSelectedContact(contact)}
                    >
                      <div className="contact-name">{contact.name || 'Unknown'}</div>
                      <div className="contact-details">
                        {contact.email && <span className="contact-email">{contact.email}</span>}
                        {contact.phone && <span className="contact-phone">{contact.phone}</span>}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="manual-entry">
                <p>Or enter manually:</p>
                <div className="manual-fields">
                  <input
                    type="text"
                    placeholder="Name"
                    value={manualName}
                    onChange={(e) => setManualName(e.target.value)}
                  />
                  {channel === 'email' ? (
                    <input
                      type="email"
                      placeholder="Email address"
                      value={manualEmail}
                      onChange={(e) => setManualEmail(e.target.value)}
                    />
                  ) : (
                    <input
                      type="tel"
                      placeholder="Phone number"
                      value={manualPhone}
                      onChange={(e) => setManualPhone(e.target.value)}
                    />
                  )}
                </div>
              </div>
            </div>

            {/* Template Selection */}
            <div className="form-section">
              <h3>3. Choose Message</h3>
              <div className="template-list">
                {templates.map(template => (
                  <div
                    key={template.id}
                    className={`template-item ${selectedTemplate?.id === template.id ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedTemplate(template);
                      setCustomMessage('');
                    }}
                  >
                    <div className="template-name">{template.name}</div>
                    <div className="template-desc">{template.description}</div>
                    {template.subject && (
                      <div className="template-subject">Subject: {template.subject}</div>
                    )}
                  </div>
                ))}
              </div>

              <div className="custom-message">
                <p>Or write a custom message:</p>
                {channel === 'email' && (
                  <input
                    type="text"
                    placeholder="Subject line"
                    value={customSubject}
                    onChange={(e) => setCustomSubject(e.target.value)}
                    className="subject-input"
                  />
                )}
                <textarea
                  placeholder="Enter your message here... Use {first_name} to personalize."
                  value={customMessage}
                  onChange={(e) => {
                    setCustomMessage(e.target.value);
                    if (e.target.value) setSelectedTemplate(null);
                  }}
                  rows={5}
                />
              </div>
            </div>

            {/* Preview & Send */}
            <div className="form-section">
              <h3>4. Send</h3>
              <div className="preview-box">
                <div className="preview-header">Preview</div>
                <div className="preview-content">
                  <p><strong>To:</strong> {selectedContact?.email || selectedContact?.phone || manualEmail || manualPhone || '(select recipient)'}</p>
                  <p><strong>Channel:</strong> {channel.toUpperCase()}</p>
                  {channel === 'email' && (
                    <p><strong>Subject:</strong> {customSubject || selectedTemplate?.subject || '(select template)'}</p>
                  )}
                  <p><strong>Message:</strong></p>
                  <div className="preview-message">
                    {(customMessage || selectedTemplate?.message || '(select template or write message)')
                      .replace(/{first_name}/g, manualName || selectedContact?.name?.split(' ')[0] || 'there')}
                  </div>
                </div>
              </div>

              <button
                className="send-btn"
                onClick={handleSendOutreach}
                disabled={sending}
              >
                {sending ? 'Sending...' : `Send ${channel === 'email' ? 'Email' : 'SMS'}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Conversations Tab */}
      {activeTab === 'conversations' && (
        <div className="conversations-container">
          <div className="conversations-list">
            <div className="list-header">
              <h3>Active Conversations</h3>
              <button onClick={fetchConversations} className="refresh-btn">Refresh</button>
            </div>
            {conversations.length === 0 ? (
              <div className="no-conversations">No conversations yet. Send your first outreach!</div>
            ) : (
              conversations.map(conv => (
                <div
                  key={conv.id}
                  className={`conversation-item ${selectedConversation === conv.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedConversation(conv.id);
                    fetchConversationDetail(conv.id);
                  }}
                >
                  <div className="conv-header">
                    <span className="conv-name">{conv.contact_name}</span>
                    <span className={`conv-channel ${conv.channel}`}>{conv.channel}</span>
                  </div>
                  <div className="conv-contact">
                    {conv.contact_email || conv.contact_phone}
                  </div>
                  <div className="conv-meta">
                    <span className="conv-messages">{conv.message_count} messages</span>
                    <span className="conv-date">{formatDate(conv.created_at)}</span>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="conversation-detail">
            {selectedConversation && conversationDetail ? (
              <>
                <div className="detail-header">
                  <h3>Conversation History</h3>
                  <span className={`stage-badge ${conversationDetail.stage}`}>
                    {conversationDetail.stage}
                  </span>
                </div>
                <div className="messages-list">
                  {conversationDetail.messages && conversationDetail.messages.length > 0 ? (
                    conversationDetail.messages.map((msg, idx) => (
                      <div key={idx} className={`message ${msg.role}`}>
                        <div className="message-header">
                          <span className="message-role">
                            {msg.role === 'assistant' ? 'Sarah (AI)' : 'Customer'}
                          </span>
                          <span className="message-time">{formatDate(msg.timestamp)}</span>
                        </div>
                        <div className="message-content">{msg.content}</div>
                      </div>
                    ))
                  ) : (
                    <div className="no-messages">No messages yet</div>
                  )}
                </div>
                {conversationDetail.collected_info && Object.keys(conversationDetail.collected_info).length > 0 && (
                  <div className="collected-info">
                    <h4>Collected Information</h4>
                    <ul>
                      {Object.entries(conversationDetail.collected_info).map(([key, value]) => (
                        <li key={key}><strong>{key}:</strong> {String(value)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="no-selection">
                Select a conversation to view details
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stats Tab */}
      {activeTab === 'stats' && stats && (
        <div className="stats-container">
          <div className="stats-header">
            <h3>Outreach Statistics (Last 30 Days)</h3>
            <button onClick={fetchStats} className="refresh-btn">Refresh</button>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.total_sent || 0}</div>
              <div className="stat-label">Total Sent</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.total_successful || 0}</div>
              <div className="stat-label">Successful</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.by_channel?.email?.total_sent || 0}</div>
              <div className="stat-label">Emails Sent</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.by_channel?.sms?.total_sent || 0}</div>
              <div className="stat-label">SMS Sent</div>
            </div>
          </div>

          <div className="stats-details">
            <h4>By Channel</h4>
            <table>
              <thead>
                <tr>
                  <th>Channel</th>
                  <th>Total Sent</th>
                  <th>Successful</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats.by_channel || {}).map(([channel, data]) => (
                  <tr key={channel}>
                    <td>{channel.toUpperCase()}</td>
                    <td>{data.total_sent}</td>
                    <td>{data.successful}</td>
                    <td>{data.failed}</td>
                  </tr>
                ))}
                {Object.keys(stats.by_channel || {}).length === 0 && (
                  <tr>
                    <td colSpan={4} className="no-data">No data yet</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIOutreach;
