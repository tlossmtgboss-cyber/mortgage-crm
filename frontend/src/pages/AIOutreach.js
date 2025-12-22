import React, { useState, useEffect, useCallback } from 'react';
import './AIOutreach.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const AIOutreach = () => {
  const [activeTab, setActiveTab] = useState('send'); // send, conversations, campaigns, triggers, stats
  const [contacts, setContacts] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [message, setMessage] = useState(null);

  // Form state
  const [selectedContacts, setSelectedContacts] = useState([]);
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

  // Campaigns and Triggers state
  const [campaigns, setCampaigns] = useState([]);
  const [triggers, setTriggers] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [campaignDetail, setCampaignDetail] = useState(null);

  // Speech recognition state
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);

  // Check for speech recognition support
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    setSpeechSupported(!!SpeechRecognition);
  }, []);

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessage({ type: 'error', text: 'Speech recognition not supported in this browser' });
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript) {
        setCustomMessage(prev => prev + (prev ? ' ' : '') + finalTranscript);
        setSelectedTemplate(null);
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'not-allowed') {
        setMessage({ type: 'error', text: 'Microphone access denied. Please allow microphone access.' });
      }
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();

    // Store recognition instance for stopping
    window.currentRecognition = recognition;
  };

  const stopListening = () => {
    if (window.currentRecognition) {
      window.currentRecognition.stop();
      window.currentRecognition = null;
    }
    setIsListening(false);
  };

  const toggleListening = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

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
      // Use SMS conversations endpoint which has proper two-way conversation data
      const response = await fetch(`${API_BASE}/api/v1/sms/conversations`, {
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
      const response = await fetch(`${API_BASE}/api/v1/sms/conversations/${convId}/messages`, {
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

  // Send reply in conversation
  const sendConversationReply = async (message) => {
    if (!selectedConversation || !message.trim()) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/sms/conversations/${selectedConversation}/send`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ message: message.trim() })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Reply sent!' });
        fetchConversationDetail(selectedConversation);
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to send reply' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error sending reply' });
    }
  };

  // Approve an AI message (mark as good)
  const approveMessage = async (messageId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/sms/messages/${messageId}/feedback`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ feedback: 'approved', rating: 5 })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Message approved!' });
        fetchConversationDetail(selectedConversation);
      }
    } catch (err) {
      console.error('Error approving message:', err);
    }
  };

  // Reject/give feedback on AI message
  const rejectMessage = async (messageId, feedback) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/sms/messages/${messageId}/feedback`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ feedback: feedback || 'needs_improvement', rating: 2 })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Feedback submitted!' });
        fetchConversationDetail(selectedConversation);
      }
    } catch (err) {
      console.error('Error submitting feedback:', err);
    }
  };

  const fetchCampaigns = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/campaigns`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setCampaigns(data.campaigns || []);
      }
    } catch (err) {
      console.error('Error fetching campaigns:', err);
    }
  }, []);

  const fetchTriggers = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/triggers`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTriggers(data.triggers || []);
      }
    } catch (err) {
      console.error('Error fetching triggers:', err);
    }
  }, []);

  const fetchCampaignDetail = async (campaignId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/campaigns/${campaignId}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setCampaignDetail(data);
      }
    } catch (err) {
      console.error('Error fetching campaign detail:', err);
    }
  };

  const setupDefaultTriggers = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/triggers/setup-defaults`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setMessage({ type: 'success', text: `Created ${data.created} default triggers` });
        fetchTriggers();
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error setting up triggers' });
    }
  };

  const toggleTrigger = async (triggerId, isActive) => {
    try {
      const trigger = triggers.find(t => t.id === triggerId);
      if (!trigger) return;

      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/triggers/${triggerId}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          ...trigger,
          is_active: !isActive
        })
      });
      if (response.ok) {
        fetchTriggers();
      }
    } catch (err) {
      console.error('Error toggling trigger:', err);
    }
  };

  const updateCampaignStatus = async (campaignId, status) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/automated-outreach/campaigns/${campaignId}/status?status=${status}`, {
        method: 'PUT',
        headers: getAuthHeaders()
      });
      if (response.ok) {
        setMessage({ type: 'success', text: `Campaign ${status}` });
        fetchCampaigns();
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error updating campaign' });
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchContacts(), fetchTemplates(), fetchConversations(), fetchStats(), fetchCampaigns(), fetchTriggers()]);
      setLoading(false);
    };
    loadData();
  }, [fetchContacts, fetchTemplates, fetchConversations, fetchStats, fetchCampaigns, fetchTriggers]);

  useEffect(() => {
    fetchTemplates();
  }, [channel, fetchTemplates]);

  useEffect(() => {
    const delaySearch = setTimeout(() => {
      fetchContacts();
    }, 300);
    return () => clearTimeout(delaySearch);
  }, [searchTerm, fetchContacts]);

  // Helper functions for multi-select
  const toggleContactSelection = (contact) => {
    setSelectedContacts(prev => {
      const isSelected = prev.some(c => c.id === contact.id);
      if (isSelected) {
        return prev.filter(c => c.id !== contact.id);
      } else {
        return [...prev, contact];
      }
    });
  };

  const selectAllContacts = () => {
    const filteredContacts = contacts.filter(c =>
      channel === 'email' ? c.email : c.phone
    );
    setSelectedContacts(filteredContacts);
  };

  const deselectAllContacts = () => {
    setSelectedContacts([]);
  };

  const isAllSelected = () => {
    const filteredContacts = contacts.filter(c =>
      channel === 'email' ? c.email : c.phone
    );
    return filteredContacts.length > 0 && filteredContacts.every(c =>
      selectedContacts.some(sc => sc.id === c.id)
    );
  };

  const handleSendOutreach = async () => {
    // Validate
    const hasManualRecipient = channel === 'email' ? manualEmail : manualPhone;
    if (selectedContacts.length === 0 && !hasManualRecipient) {
      setMessage({ type: 'error', text: `Please select at least one contact or enter ${channel === 'email' ? 'an email address' : 'a phone number'}` });
      return;
    }
    if (!selectedTemplate && !customMessage) {
      setMessage({ type: 'error', text: 'Please select a template or enter a custom message' });
      return;
    }

    setSending(true);
    setMessage(null);

    try {
      let successCount = 0;
      let failCount = 0;
      const recipients = [...selectedContacts];

      // Add manual entry if provided
      if (hasManualRecipient) {
        recipients.push({
          id: null,
          name: manualName || 'there',
          email: manualEmail,
          phone: manualPhone
        });
      }

      // Send to each recipient
      for (const contact of recipients) {
        const payload = {
          channel: channel,
          template_id: selectedTemplate?.id || null,
          custom_message: customMessage || null,
          contact_id: contact.id,
          email: contact.email,
          phone: contact.phone,
          first_name: contact.name?.split(' ')[0] || 'there'
        };

        try {
          const response = await fetch(`${API_BASE}/api/v1/ai-outreach/start`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
          });

          const data = await response.json();
          if (response.ok && data.success) {
            successCount++;
          } else {
            failCount++;
          }
        } catch (err) {
          failCount++;
        }
      }

      if (successCount > 0) {
        setMessage({
          type: failCount > 0 ? 'warning' : 'success',
          text: `Sent to ${successCount} recipient${successCount !== 1 ? 's' : ''}${failCount > 0 ? `, ${failCount} failed` : ''}`
        });
        // Reset form
        setSelectedContacts([]);
        setSelectedTemplate(null);
        setCustomMessage('');
        setManualEmail('');
        setManualPhone('');
        setManualName('');
        // Refresh conversations
        fetchConversations();
        fetchStats();
      } else {
        setMessage({ type: 'error', text: 'Failed to send outreach to any recipients' });
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
          className={`tab-btn ${activeTab === 'automation' ? 'active' : ''}`}
          onClick={() => setActiveTab('automation')}
        >
          Automation
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
              <h3>2. Select Recipients {selectedContacts.length > 0 && <span className="selected-count">({selectedContacts.length} selected)</span>}</h3>
              <div className="contact-search">
                <input
                  type="text"
                  placeholder="Search contacts by name, email, or phone..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>

              {/* Select All / Deselect All */}
              {contacts.length > 0 && (
                <div className="select-all-row">
                  <label className="select-all-checkbox">
                    <input
                      type="checkbox"
                      checked={isAllSelected()}
                      onChange={() => isAllSelected() ? deselectAllContacts() : selectAllContacts()}
                    />
                    <span>Select All ({contacts.filter(c => channel === 'email' ? c.email : c.phone).length})</span>
                  </label>
                  {selectedContacts.length > 0 && (
                    <button className="clear-selection-btn" onClick={deselectAllContacts}>
                      Clear Selection
                    </button>
                  )}
                </div>
              )}

              <div className="contact-list">
                {contacts.length === 0 ? (
                  <div className="no-contacts">No contacts found</div>
                ) : (
                  contacts.map(contact => {
                    const hasRequiredField = channel === 'email' ? contact.email : contact.phone;
                    const isSelected = selectedContacts.some(c => c.id === contact.id);
                    return (
                      <div
                        key={contact.id}
                        className={`contact-item ${isSelected ? 'selected' : ''} ${!hasRequiredField ? 'disabled' : ''}`}
                        onClick={() => hasRequiredField && toggleContactSelection(contact)}
                      >
                        <div className="contact-checkbox">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            disabled={!hasRequiredField}
                            onChange={() => hasRequiredField && toggleContactSelection(contact)}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </div>
                        <div className="contact-info">
                          <div className="contact-name">{contact.name || 'Unknown'}</div>
                          <div className="contact-details">
                            {contact.email && <span className={`contact-email ${channel === 'email' ? 'highlight' : ''}`}>{contact.email}</span>}
                            {contact.phone && <span className={`contact-phone ${channel === 'sms' ? 'highlight' : ''}`}>{contact.phone}</span>}
                          </div>
                        </div>
                        {!hasRequiredField && (
                          <div className="missing-field">No {channel === 'email' ? 'email' : 'phone'}</div>
                        )}
                      </div>
                    );
                  })
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
                <div className="textarea-wrapper">
                  <textarea
                    placeholder="Enter your message here... Use {first_name} to personalize. Click the mic to speak."
                    value={customMessage}
                    onChange={(e) => {
                      setCustomMessage(e.target.value);
                      if (e.target.value) setSelectedTemplate(null);
                    }}
                    rows={5}
                  />
                  {speechSupported && (
                    <button
                      type="button"
                      className={`voice-btn ${isListening ? 'listening' : ''}`}
                      onClick={toggleListening}
                      title={isListening ? 'Stop listening' : 'Click to speak'}
                    >
                      {isListening ? '🔴' : '🎤'}
                    </button>
                  )}
                </div>
                {isListening && (
                  <div className="listening-indicator">
                    Listening... Speak now
                  </div>
                )}
              </div>
            </div>

            {/* Preview & Send */}
            <div className="form-section">
              <h3>4. Send</h3>
              <div className="preview-box">
                <div className="preview-header">Preview</div>
                <div className="preview-content">
                  <p><strong>To:</strong> {
                    selectedContacts.length > 0
                      ? `${selectedContacts.length} recipient${selectedContacts.length !== 1 ? 's' : ''} selected`
                      : (manualEmail || manualPhone || '(select recipients)')
                  }</p>
                  {selectedContacts.length > 0 && selectedContacts.length <= 5 && (
                    <div className="recipients-preview">
                      {selectedContacts.map(c => (
                        <span key={c.id} className="recipient-chip">
                          {c.name?.split(' ')[0] || (channel === 'email' ? c.email : c.phone)}
                        </span>
                      ))}
                    </div>
                  )}
                  <p><strong>Channel:</strong> {channel.toUpperCase()}</p>
                  {channel === 'email' && (
                    <p><strong>Subject:</strong> {customSubject || selectedTemplate?.subject || '(select template)'}</p>
                  )}
                  <p><strong>Message:</strong></p>
                  <div className="preview-message">
                    {(customMessage || selectedTemplate?.message || selectedTemplate?.body || '(select template or write message)')
                      .replace(/{first_name}/g, '{first_name}')}
                  </div>
                </div>
              </div>

              <button
                className="send-btn"
                onClick={handleSendOutreach}
                disabled={sending}
              >
                {sending
                  ? `Sending to ${selectedContacts.length + (manualEmail || manualPhone ? 1 : 0)} recipient${selectedContacts.length !== 1 ? 's' : ''}...`
                  : `Send ${channel === 'email' ? 'Email' : 'SMS'} to ${selectedContacts.length + (manualEmail || manualPhone ? 1 : 0)} recipient${(selectedContacts.length + (manualEmail || manualPhone ? 1 : 0)) !== 1 ? 's' : ''}`
                }
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
                    <span className="conv-name">{conv.contact_name || 'Unknown'}</span>
                    <span className="conv-channel sms">SMS</span>
                  </div>
                  <div className="conv-contact">
                    {conv.phone_number}
                  </div>
                  <div className="conv-meta">
                    <span className="conv-messages">{conv.message_count} messages</span>
                    <span className="conv-date">{formatDate(conv.last_message_at)}</span>
                  </div>
                  {conv.ai_enabled && (
                    <div className="conv-ai-badge">AI Enabled</div>
                  )}
                </div>
              ))
            )}
          </div>

          <div className="conversation-detail">
            {selectedConversation && conversationDetail ? (
              <>
                <div className="detail-header">
                  <h3>{conversationDetail.conversation?.contact_name || 'Conversation'}</h3>
                  <div className="detail-meta">
                    <span className="detail-phone">{conversationDetail.conversation?.phone_number}</span>
                    {conversationDetail.conversation?.ai_enabled && (
                      <span className="ai-badge">AI Enabled</span>
                    )}
                  </div>
                </div>
                <div className="messages-list">
                  {conversationDetail.messages && conversationDetail.messages.length > 0 ? (
                    conversationDetail.messages.map((msg) => (
                      <div key={msg.id} className={`message ${msg.direction}`}>
                        <div className="message-header">
                          <span className="message-role">
                            {msg.direction === 'outbound' ? (msg.ai_generated ? 'Sarah (AI)' : 'You') : 'Customer'}
                          </span>
                          <span className="message-time">{formatDate(msg.created_at)}</span>
                        </div>
                        <div className="message-content">{msg.message}</div>
                        <div className="message-footer">
                          <span className={`message-status ${msg.status}`}>{msg.status}</span>
                          {msg.ai_generated && (
                            <div className="message-actions">
                              <button
                                className="approve-btn"
                                onClick={(e) => { e.stopPropagation(); approveMessage(msg.id); }}
                                title="Approve this response"
                              >
                                Approve
                              </button>
                              <button
                                className="feedback-btn"
                                onClick={(e) => { e.stopPropagation(); rejectMessage(msg.id); }}
                                title="This needs improvement"
                              >
                                Needs Work
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="no-messages">No messages yet</div>
                  )}
                </div>

                {/* Reply Box */}
                <div className="reply-box">
                  <input
                    type="text"
                    placeholder="Type a reply..."
                    className="reply-input"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter' && e.target.value.trim()) {
                        sendConversationReply(e.target.value);
                        e.target.value = '';
                      }
                    }}
                  />
                  <button
                    className="send-reply-btn"
                    onClick={(e) => {
                      const input = e.target.previousSibling;
                      if (input.value.trim()) {
                        sendConversationReply(input.value);
                        input.value = '';
                      }
                    }}
                  >
                    Send
                  </button>
                </div>
              </>
            ) : (
              <div className="no-selection">
                Select a conversation to view details
              </div>
            )}
          </div>
        </div>
      )}

      {/* Automation Tab */}
      {activeTab === 'automation' && (
        <div className="automation-container">
          <div className="automation-section">
            <div className="section-header">
              <h3>Automatic Triggers</h3>
              <p className="section-desc">Messages sent automatically when events occur</p>
              {triggers.length === 0 && (
                <button onClick={setupDefaultTriggers} className="setup-btn">
                  Setup Default Triggers
                </button>
              )}
            </div>

            <div className="triggers-list">
              {triggers.length === 0 ? (
                <div className="no-items">
                  No triggers configured. Click "Setup Default Triggers" to get started.
                </div>
              ) : (
                triggers.map(trigger => (
                  <div key={trigger.id} className={`trigger-item ${trigger.is_active ? 'active' : 'inactive'}`}>
                    <div className="trigger-header">
                      <span className="trigger-name">{trigger.name}</span>
                      <div className="trigger-badges">
                        <span className={`trigger-channel ${trigger.channel}`}>{trigger.channel}</span>
                        <span className={`trigger-type`}>{trigger.trigger_type.replace('_', ' ')}</span>
                      </div>
                    </div>
                    <div className="trigger-message">{trigger.message?.substring(0, 100)}...</div>
                    <div className="trigger-actions">
                      <label className="toggle-switch">
                        <input
                          type="checkbox"
                          checked={trigger.is_active}
                          onChange={() => toggleTrigger(trigger.id, trigger.is_active)}
                        />
                        <span className="toggle-slider"></span>
                      </label>
                      <span className="toggle-label">{trigger.is_active ? 'Active' : 'Inactive'}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="automation-section">
            <div className="section-header">
              <h3>Drip Campaigns</h3>
              <p className="section-desc">Automated message sequences over time</p>
            </div>

            <div className="campaigns-list">
              {campaigns.length === 0 ? (
                <div className="no-items">
                  No campaigns yet. Campaigns let you send a sequence of messages over days.
                </div>
              ) : (
                campaigns.map(campaign => (
                  <div
                    key={campaign.id}
                    className={`campaign-item ${campaign.status}`}
                    onClick={() => {
                      setSelectedCampaign(campaign.id);
                      fetchCampaignDetail(campaign.id);
                    }}
                  >
                    <div className="campaign-header">
                      <span className="campaign-name">{campaign.name}</span>
                      <span className={`campaign-status ${campaign.status}`}>{campaign.status}</span>
                    </div>
                    <div className="campaign-desc">{campaign.description || 'No description'}</div>
                    <div className="campaign-meta">
                      <span>{campaign.step_count} steps</span>
                      <span>{campaign.active_leads} active leads</span>
                    </div>
                    <div className="campaign-actions">
                      {campaign.status === 'draft' && (
                        <button
                          className="action-btn activate"
                          onClick={(e) => { e.stopPropagation(); updateCampaignStatus(campaign.id, 'active'); }}
                        >
                          Activate
                        </button>
                      )}
                      {campaign.status === 'active' && (
                        <button
                          className="action-btn pause"
                          onClick={(e) => { e.stopPropagation(); updateCampaignStatus(campaign.id, 'paused'); }}
                        >
                          Pause
                        </button>
                      )}
                      {campaign.status === 'paused' && (
                        <button
                          className="action-btn resume"
                          onClick={(e) => { e.stopPropagation(); updateCampaignStatus(campaign.id, 'active'); }}
                        >
                          Resume
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {selectedCampaign && campaignDetail && (
              <div className="campaign-detail">
                <h4>Campaign Steps</h4>
                <div className="steps-timeline">
                  {campaignDetail.steps?.map((step, idx) => (
                    <div key={step.id} className="step-item">
                      <div className="step-number">{idx + 1}</div>
                      <div className="step-content">
                        <div className="step-timing">
                          {step.delay_days > 0 && `${step.delay_days} day${step.delay_days > 1 ? 's' : ''} `}
                          {step.delay_hours > 0 && `${step.delay_hours} hour${step.delay_hours > 1 ? 's' : ''} `}
                          {step.delay_days === 0 && step.delay_hours === 0 && 'Immediately'}
                          after previous
                        </div>
                        <div className="step-channel">{step.channel}</div>
                        {step.subject && <div className="step-subject">Subject: {step.subject}</div>}
                        <div className="step-message">{step.message?.substring(0, 80)}...</div>
                      </div>
                    </div>
                  ))}
                </div>

                {campaignDetail.assigned_leads?.length > 0 && (
                  <div className="assigned-leads">
                    <h4>Assigned Leads ({campaignDetail.assigned_leads.length})</h4>
                    <div className="leads-list">
                      {campaignDetail.assigned_leads.slice(0, 10).map(lead => (
                        <div key={lead.id} className="lead-item">
                          <span className="lead-name">{lead.first_name} {lead.last_name}</span>
                          <span className="lead-step">Step {lead.current_step}</span>
                          <span className={`lead-status ${lead.status}`}>{lead.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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
