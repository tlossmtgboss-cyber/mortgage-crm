import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  getTransaction,
  addParty,
  sendPortalInvite,
  updateMilestone,
  sendMessageAsLO,
  getMessages,
  formatCurrency,
  formatDate,
  getStatusInfo,
  getMilestoneStatusInfo,
  getRoleDisplayName,
} from '../services/listingPortalApi';
import './ListingPortalTransactionDetail.css';

const ListingPortalTransactionDetail = () => {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const messagesEndRef = useRef(null);

  const [transaction, setTransaction] = useState(null);
  const [parties, setParties] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [messages, setMessages] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal states
  const [showAddPartyModal, setShowAddPartyModal] = useState(false);
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [selectedMilestone, setSelectedMilestone] = useState(null);

  // Form states
  const [partyForm, setPartyForm] = useState({
    role: 'listing_agent',
    email: '',
    first_name: '',
    last_name: '',
    phone: '',
    company_name: '',
    license_number: '',
    notify_weekly_updates: true,
    notify_milestone_changes: true,
    notify_messages: true,
  });
  const [addingParty, setAddingParty] = useState(false);
  const [sendingInvite, setSendingInvite] = useState({});

  // Messaging
  const [messageText, setMessageText] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  const fetchTransaction = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getTransaction(transactionId);
      const data = response.data;
      setTransaction(data.transaction);
      setParties(data.parties || []);
      setMilestones(data.milestones || []);
      setUnreadCount(data.unread_messages || 0);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch transaction:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [transactionId]);

  const fetchMessages = useCallback(async () => {
    try {
      const response = await getMessages(transactionId);
      setMessages(response.data?.messages || []);
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  }, [transactionId]);

  useEffect(() => {
    fetchTransaction();
  }, [fetchTransaction]);

  useEffect(() => {
    if (activeTab === 'messages') {
      fetchMessages();
    }
  }, [activeTab, fetchMessages]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleAddParty = async (e) => {
    e.preventDefault();
    if (!partyForm.email || !partyForm.first_name || !partyForm.last_name) {
      toast.error('Please fill in required fields');
      return;
    }

    try {
      setAddingParty(true);
      await addParty(transactionId, partyForm);
      setShowAddPartyModal(false);
      setPartyForm({
        role: 'listing_agent',
        email: '',
        first_name: '',
        last_name: '',
        phone: '',
        company_name: '',
        license_number: '',
        notify_weekly_updates: true,
        notify_milestone_changes: true,
        notify_messages: true,
      });
      fetchTransaction();
    } catch (err) {
      console.error('Failed to add party:', err);
      toast.error('Failed to add party: ' + err.message);
    } finally {
      setAddingParty(false);
    }
  };

  const handleSendInvite = async (partyId) => {
    try {
      setSendingInvite((prev) => ({ ...prev, [partyId]: true }));
      await sendPortalInvite(transactionId, partyId);
      toast.success('Portal invite sent successfully!');
    } catch (err) {
      console.error('Failed to send invite:', err);
      toast.error('Failed to send invite: ' + err.message);
    } finally {
      setSendingInvite((prev) => ({ ...prev, [partyId]: false }));
    }
  };

  const handleUpdateMilestone = async (status) => {
    if (!selectedMilestone) return;

    try {
      await updateMilestone(transactionId, selectedMilestone.id, {
        status,
        completed_at: status === 'completed' ? new Date().toISOString() : null,
      });
      setShowMilestoneModal(false);
      setSelectedMilestone(null);
      fetchTransaction();
    } catch (err) {
      console.error('Failed to update milestone:', err);
      toast.error('Failed to update milestone: ' + err.message);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!messageText.trim()) return;

    try {
      setSendingMessage(true);
      await sendMessageAsLO(transactionId, messageText.trim());
      setMessageText('');
      fetchMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
      toast.error('Failed to send message: ' + err.message);
    } finally {
      setSendingMessage(false);
    }
  };

  if (loading) {
    return (
      <div className="listing-portal-detail">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading transaction...</p>
        </div>
      </div>
    );
  }

  if (error || !transaction) {
    return (
      <div className="listing-portal-detail">
        <div className="error-state">
          <h2>Error Loading Transaction</h2>
          <p>{error || 'Transaction not found'}</p>
          <button className="btn-secondary" onClick={() => navigate('/listing-portal')}>
            Back to Transactions
          </button>
        </div>
      </div>
    );
  }

  const statusInfo = getStatusInfo(transaction.current_status);
  const completedMilestones = milestones.filter((m) => m.status === 'completed').length;
  const progress = milestones.length > 0 ? (completedMilestones / milestones.length) * 100 : 0;

  return (
    <div className="listing-portal-detail">
      {/* Header */}
      <header className="detail-header">
        <button className="back-btn" onClick={() => navigate('/listing-portal')}>
          &larr; Back to Transactions
        </button>

        <div className="header-main">
          <div className="header-info">
            <h1>{transaction.property_address}</h1>
            <p className="location">
              {[transaction.property_city, transaction.property_state, transaction.property_zip]
                .filter(Boolean)
                .join(', ')}
            </p>
          </div>
          <span
            className="status-badge large"
            style={{ backgroundColor: statusInfo.bg, color: statusInfo.color }}
          >
            {statusInfo.label}
          </span>
        </div>

        <div className="header-meta">
          {transaction.purchase_price && (
            <div className="meta-item">
              <span className="meta-label">Purchase Price</span>
              <span className="meta-value">{formatCurrency(transaction.purchase_price)}</span>
            </div>
          )}
          {transaction.target_close_date && (
            <div className="meta-item">
              <span className="meta-label">Target Close</span>
              <span className="meta-value">{formatDate(transaction.target_close_date)}</span>
            </div>
          )}
          <div className="meta-item">
            <span className="meta-label">Parties</span>
            <span className="meta-value">{parties.length}</span>
          </div>
          <div className="meta-item">
            <span className="meta-label">Progress</span>
            <span className="meta-value">{Math.round(progress)}%</span>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="tabs-container">
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`tab ${activeTab === 'parties' ? 'active' : ''}`}
            onClick={() => setActiveTab('parties')}
          >
            Parties ({parties.length})
          </button>
          <button
            className={`tab ${activeTab === 'milestones' ? 'active' : ''}`}
            onClick={() => setActiveTab('milestones')}
          >
            Milestones
          </button>
          <button
            className={`tab ${activeTab === 'messages' ? 'active' : ''}`}
            onClick={() => setActiveTab('messages')}
          >
            Messages
            {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="overview-grid">
              {/* Progress Card */}
              <div className="overview-card">
                <h3>Transaction Progress</h3>
                <div className="progress-ring-container">
                  <svg className="progress-ring" viewBox="0 0 120 120">
                    <circle
                      className="progress-ring-bg"
                      cx="60"
                      cy="60"
                      r="52"
                      fill="none"
                      strokeWidth="12"
                    />
                    <circle
                      className="progress-ring-fill"
                      cx="60"
                      cy="60"
                      r="52"
                      fill="none"
                      strokeWidth="12"
                      strokeDasharray={`${progress * 3.27} 327`}
                      transform="rotate(-90 60 60)"
                    />
                  </svg>
                  <div className="progress-text">
                    <span className="progress-value">{Math.round(progress)}%</span>
                    <span className="progress-label">Complete</span>
                  </div>
                </div>
                <p className="progress-detail">
                  {completedMilestones} of {milestones.length} milestones completed
                </p>
              </div>

              {/* Parties Preview */}
              <div className="overview-card">
                <div className="card-header-row">
                  <h3>Parties</h3>
                  <button className="btn-link" onClick={() => setActiveTab('parties')}>
                    View All
                  </button>
                </div>
                {parties.length === 0 ? (
                  <p className="empty-text">No parties added yet</p>
                ) : (
                  <ul className="parties-preview">
                    {parties.slice(0, 3).map((party) => (
                      <li key={party.id}>
                        <div className="party-avatar">
                          {party.first_name?.[0]}
                          {party.last_name?.[0]}
                        </div>
                        <div className="party-info">
                          <span className="party-name">
                            {party.first_name} {party.last_name}
                          </span>
                          <span className="party-role">{getRoleDisplayName(party.role)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                <button className="btn-secondary full-width" onClick={() => setShowAddPartyModal(true)}>
                  + Add Party
                </button>
              </div>

              {/* Recent Milestones */}
              <div className="overview-card">
                <div className="card-header-row">
                  <h3>Milestones</h3>
                  <button className="btn-link" onClick={() => setActiveTab('milestones')}>
                    View All
                  </button>
                </div>
                {milestones.length === 0 ? (
                  <p className="empty-text">No milestones defined</p>
                ) : (
                  <ul className="milestones-preview">
                    {milestones.slice(0, 4).map((milestone) => {
                      const msStatus = getMilestoneStatusInfo(milestone.status);
                      return (
                        <li key={milestone.id} className={`milestone-${milestone.status}`}>
                          <span className="milestone-icon" style={{ color: msStatus.color }}>
                            {msStatus.icon}
                          </span>
                          <span className="milestone-name">{milestone.milestone_name}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Parties Tab */}
        {activeTab === 'parties' && (
          <div className="parties-tab">
            <div className="tab-header">
              <h2>Transaction Parties</h2>
              <button className="btn-primary" onClick={() => setShowAddPartyModal(true)}>
                + Add Party
              </button>
            </div>

            {parties.length === 0 ? (
              <div className="empty-state">
                <h3>No parties added</h3>
                <p>Add listing agents, escrow officers, and other parties to keep them informed.</p>
                <button className="btn-primary" onClick={() => setShowAddPartyModal(true)}>
                  Add First Party
                </button>
              </div>
            ) : (
              <div className="parties-grid">
                {parties.map((party) => (
                  <div key={party.id} className="party-card">
                    <div className="party-card-header">
                      <div className="party-avatar large">
                        {party.first_name?.[0]}
                        {party.last_name?.[0]}
                      </div>
                      <div>
                        <h4>
                          {party.first_name} {party.last_name}
                        </h4>
                        <span className="role-badge">{getRoleDisplayName(party.role)}</span>
                      </div>
                    </div>

                    <div className="party-card-body">
                      <div className="contact-info">
                        <div className="contact-item">
                          <svg viewBox="0 0 20 20" fill="currentColor">
                            <path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z" />
                            <path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z" />
                          </svg>
                          <span>{party.email}</span>
                        </div>
                        {party.phone && (
                          <div className="contact-item">
                            <svg viewBox="0 0 20 20" fill="currentColor">
                              <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z" />
                            </svg>
                            <span>{party.phone}</span>
                          </div>
                        )}
                        {party.company_name && (
                          <div className="contact-item">
                            <svg viewBox="0 0 20 20" fill="currentColor">
                              <path
                                fillRule="evenodd"
                                d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a1 1 0 110 2h-3a1 1 0 01-1-1v-2a1 1 0 00-1-1H9a1 1 0 00-1 1v2a1 1 0 01-1 1H4a1 1 0 110-2V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span>{party.company_name}</span>
                          </div>
                        )}
                      </div>

                      <div className="notification-prefs">
                        <span className="pref-label">Notifications:</span>
                        <div className="pref-badges">
                          {party.notify_weekly_updates && (
                            <span className="pref-badge">Weekly</span>
                          )}
                          {party.notify_milestone_changes && (
                            <span className="pref-badge">Milestones</span>
                          )}
                          {party.notify_messages && <span className="pref-badge">Messages</span>}
                        </div>
                      </div>
                    </div>

                    <div className="party-card-footer">
                      <button
                        className="btn-primary small"
                        onClick={() => handleSendInvite(party.id)}
                        disabled={sendingInvite[party.id]}
                      >
                        {sendingInvite[party.id] ? 'Sending...' : 'Send Portal Invite'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Milestones Tab */}
        {activeTab === 'milestones' && (
          <div className="milestones-tab">
            <div className="tab-header">
              <h2>Transaction Milestones</h2>
              <div className="progress-bar-container">
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${progress}%` }}></div>
                </div>
                <span className="progress-text-inline">
                  {completedMilestones}/{milestones.length} Complete
                </span>
              </div>
            </div>

            {milestones.length === 0 ? (
              <div className="empty-state">
                <h3>No milestones defined</h3>
                <p>Milestones will be automatically created based on the loan stage.</p>
              </div>
            ) : (
              <div className="milestones-timeline">
                {milestones.map((milestone, index) => {
                  const msStatus = getMilestoneStatusInfo(milestone.status);
                  return (
                    <div
                      key={milestone.id}
                      className={`milestone-item ${milestone.status}`}
                      onClick={() => {
                        setSelectedMilestone(milestone);
                        setShowMilestoneModal(true);
                      }}
                    >
                      <div className="milestone-connector">
                        <div
                          className="milestone-dot"
                          style={{
                            backgroundColor:
                              milestone.status === 'completed' ? msStatus.color : 'white',
                            borderColor: msStatus.color,
                          }}
                        >
                          {milestone.status === 'completed' && (
                            <svg viewBox="0 0 20 20" fill="white">
                              <path
                                fillRule="evenodd"
                                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </div>
                        {index < milestones.length - 1 && <div className="milestone-line"></div>}
                      </div>

                      <div className="milestone-content">
                        <div className="milestone-header">
                          <h4>{milestone.milestone_name}</h4>
                          <span
                            className="milestone-status-badge"
                            style={{ color: msStatus.color }}
                          >
                            {msStatus.label}
                          </span>
                        </div>
                        {milestone.description && (
                          <p className="milestone-description">{milestone.description}</p>
                        )}
                        <div className="milestone-meta">
                          {milestone.target_date && (
                            <span>Target: {formatDate(milestone.target_date)}</span>
                          )}
                          {milestone.completed_at && (
                            <span>Completed: {formatDate(milestone.completed_at)}</span>
                          )}
                        </div>
                      </div>

                      <div className="milestone-action">
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path
                            fillRule="evenodd"
                            d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Messages Tab */}
        {activeTab === 'messages' && (
          <div className="messages-tab">
            <div className="tab-header">
              <h2>Messages</h2>
            </div>

            <div className="messages-container">
              <div className="messages-list">
                {messages.length === 0 ? (
                  <div className="empty-messages">
                    <p>No messages yet. Start the conversation!</p>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`message ${msg.sender_type === 'lo' ? 'outgoing' : 'incoming'}`}
                    >
                      <div className="message-header">
                        <span className="sender-name">{msg.sender_name}</span>
                        <span className="message-time">{formatDate(msg.created_at)}</span>
                      </div>
                      <div className="message-content">{msg.content}</div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              <form className="message-input-form" onSubmit={handleSendMessage}>
                <input
                  type="text"
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="Type a message..."
                  disabled={sendingMessage}
                />
                <button type="submit" className="btn-primary" disabled={sendingMessage || !messageText.trim()}>
                  {sendingMessage ? 'Sending...' : 'Send'}
                </button>
              </form>
            </div>
          </div>
        )}
      </div>

      {/* Add Party Modal */}
      {showAddPartyModal && (
        <div className="modal-overlay" onClick={() => setShowAddPartyModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add Party</h2>
              <button className="close-btn" onClick={() => setShowAddPartyModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleAddParty}>
              <div className="form-group">
                <label>Role *</label>
                <select
                  value={partyForm.role}
                  onChange={(e) => setPartyForm((p) => ({ ...p, role: e.target.value }))}
                >
                  <option value="listing_agent">Listing Agent</option>
                  <option value="selling_agent">Selling Agent</option>
                  <option value="escrow_officer">Escrow Officer</option>
                  <option value="title_officer">Title Officer</option>
                  <option value="attorney">Attorney</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={partyForm.first_name}
                    onChange={(e) => setPartyForm((p) => ({ ...p, first_name: e.target.value }))}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={partyForm.last_name}
                    onChange={(e) => setPartyForm((p) => ({ ...p, last_name: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  value={partyForm.email}
                  onChange={(e) => setPartyForm((p) => ({ ...p, email: e.target.value }))}
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={partyForm.phone}
                    onChange={(e) => setPartyForm((p) => ({ ...p, phone: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Company</label>
                  <input
                    type="text"
                    value={partyForm.company_name}
                    onChange={(e) => setPartyForm((p) => ({ ...p, company_name: e.target.value }))}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>License Number</label>
                <input
                  type="text"
                  value={partyForm.license_number}
                  onChange={(e) => setPartyForm((p) => ({ ...p, license_number: e.target.value }))}
                />
              </div>

              <div className="form-group">
                <label>Notification Preferences</label>
                <div className="checkbox-group">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={partyForm.notify_weekly_updates}
                      onChange={(e) =>
                        setPartyForm((p) => ({ ...p, notify_weekly_updates: e.target.checked }))
                      }
                    />
                    Weekly Updates
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={partyForm.notify_milestone_changes}
                      onChange={(e) =>
                        setPartyForm((p) => ({ ...p, notify_milestone_changes: e.target.checked }))
                      }
                    />
                    Milestone Changes
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={partyForm.notify_messages}
                      onChange={(e) =>
                        setPartyForm((p) => ({ ...p, notify_messages: e.target.checked }))
                      }
                    />
                    Messages
                  </label>
                </div>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowAddPartyModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={addingParty}>
                  {addingParty ? 'Adding...' : 'Add Party'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Milestone Modal */}
      {showMilestoneModal && selectedMilestone && (
        <div className="modal-overlay" onClick={() => setShowMilestoneModal(false)}>
          <div className="modal-content small" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Update Milestone</h2>
              <button className="close-btn" onClick={() => setShowMilestoneModal(false)}>
                &times;
              </button>
            </div>

            <div className="milestone-modal-content">
              <h3>{selectedMilestone.milestone_name}</h3>
              {selectedMilestone.description && <p>{selectedMilestone.description}</p>}

              <div className="milestone-status-options">
                <button
                  className={`status-option ${selectedMilestone.status === 'pending' ? 'active' : ''}`}
                  onClick={() => handleUpdateMilestone('pending')}
                >
                  <span className="status-icon">○</span>
                  Pending
                </button>
                <button
                  className={`status-option ${selectedMilestone.status === 'in_progress' ? 'active' : ''}`}
                  onClick={() => handleUpdateMilestone('in_progress')}
                >
                  <span className="status-icon">◐</span>
                  In Progress
                </button>
                <button
                  className={`status-option ${selectedMilestone.status === 'completed' ? 'active' : ''}`}
                  onClick={() => handleUpdateMilestone('completed')}
                >
                  <span className="status-icon">●</span>
                  Completed
                </button>
                <button
                  className={`status-option ${selectedMilestone.status === 'blocked' ? 'active' : ''}`}
                  onClick={() => handleUpdateMilestone('blocked')}
                >
                  <span className="status-icon warning">!</span>
                  Blocked
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ListingPortalTransactionDetail;
