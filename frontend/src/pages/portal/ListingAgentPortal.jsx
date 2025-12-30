/**
 * Listing Agent Portal
 *
 * Transaction-scoped portal for listing agents and other transaction parties.
 * Provides PII-safe view of loan progress, milestones, and messaging.
 *
 * Features:
 * - Dashboard with active transactions
 * - Milestone timeline (PII-safe)
 * - Secure messaging with LO
 * - Days-to-close countdown
 * - Notification preferences
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import listingAgentPortalApi, {
  authApi,
  dashboardApi,
  transactionApi,
  milestoneApi,
  messagingApi,
  storeSessionToken,
  clearSessionToken,
  hasValidSession,
} from '../../services/listingAgentPortalApi';
import './ListingAgentPortal.css';

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

const formatDateTime = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const getDaysUntilClose = (targetDate) => {
  if (!targetDate) return null;
  const target = new Date(targetDate);
  const today = new Date();
  const diffTime = target - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
};

const getStatusColor = (status) => {
  const colors = {
    active: '#10b981',
    pending: '#f59e0b',
    closing: '#3b82f6',
    closed: '#6b7280',
    cancelled: '#ef4444',
    on_hold: '#8b5cf6',
  };
  return colors[status] || '#6b7280';
};

const getMilestoneStatusIcon = (status) => {
  const icons = {
    completed: '✓',
    in_progress: '●',
    pending: '○',
    skipped: '—',
    blocked: '!',
  };
  return icons[status] || '○';
};

// =============================================================================
// SUB-COMPONENTS
// =============================================================================

// Loading Spinner
const LoadingSpinner = () => (
  <div className="lap-loading">
    <div className="lap-spinner"></div>
    <p>Loading your portal...</p>
  </div>
);

// Error Display
const ErrorDisplay = ({ error, onRetry }) => (
  <div className="lap-error">
    <div className="lap-error-icon">⚠️</div>
    <h2>Something went wrong</h2>
    <p>{error?.message || 'Failed to load portal'}</p>
    {onRetry && (
      <button className="lap-btn lap-btn-primary" onClick={onRetry}>
        Try Again
      </button>
    )}
  </div>
);

// Magic Link Auth Screen
const MagicLinkAuth = ({ onAuthenticate }) => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [error, setError] = useState(null);
  const [authenticating, setAuthenticating] = useState(false);

  useEffect(() => {
    if (token && !authenticating) {
      setAuthenticating(true);
      authApi.authenticateMagicLink(token)
        .then((response) => {
          storeSessionToken(response.session_token);
          onAuthenticate(response);
        })
        .catch((err) => {
          setError(err.message || 'Invalid or expired link');
          setAuthenticating(false);
        });
    }
  }, [token, onAuthenticate, authenticating]);

  if (!token) {
    return (
      <div className="lap-auth-required">
        <div className="lap-auth-icon">🔐</div>
        <h2>Access Required</h2>
        <p>Please use the link from your email to access the portal.</p>
        <p className="lap-auth-help">
          Contact your loan officer if you need a new access link.
        </p>
      </div>
    );
  }

  if (authenticating) {
    return <LoadingSpinner />;
  }

  if (error) {
    return (
      <div className="lap-auth-error">
        <div className="lap-auth-icon">⚠️</div>
        <h2>Link Expired</h2>
        <p>{error}</p>
        <p className="lap-auth-help">
          Contact your loan officer for a new access link.
        </p>
      </div>
    );
  }

  return <LoadingSpinner />;
};

// Transaction Card Component
const TransactionCard = ({ transaction, onClick, isSelected }) => {
  const daysUntilClose = getDaysUntilClose(transaction.target_close_date);

  return (
    <div
      className={`lap-transaction-card ${isSelected ? 'selected' : ''}`}
      onClick={() => onClick(transaction)}
    >
      <div className="lap-transaction-header">
        <div className="lap-property-address">{transaction.property_address}</div>
        <div
          className="lap-status-badge"
          style={{ backgroundColor: getStatusColor(transaction.current_status) }}
        >
          {transaction.current_status}
        </div>
      </div>

      <div className="lap-transaction-details">
        {transaction.property_city && (
          <div className="lap-detail">
            <span className="lap-detail-label">Location</span>
            <span className="lap-detail-value">
              {transaction.property_city}, {transaction.property_state} {transaction.property_zip}
            </span>
          </div>
        )}

        {transaction.purchase_price && (
          <div className="lap-detail">
            <span className="lap-detail-label">Purchase Price</span>
            <span className="lap-detail-value">{formatCurrency(transaction.purchase_price)}</span>
          </div>
        )}

        {transaction.target_close_date && (
          <div className="lap-detail">
            <span className="lap-detail-label">Target Close</span>
            <span className="lap-detail-value">{formatDate(transaction.target_close_date)}</span>
          </div>
        )}
      </div>

      {daysUntilClose !== null && daysUntilClose > 0 && (
        <div className="lap-days-countdown">
          <span className="lap-days-number">{daysUntilClose}</span>
          <span className="lap-days-label">days to close</span>
        </div>
      )}

      {transaction.unread_messages > 0 && (
        <div className="lap-unread-badge">{transaction.unread_messages} new</div>
      )}
    </div>
  );
};

// Milestone Timeline Component
const MilestoneTimeline = ({ milestones }) => {
  if (!milestones || milestones.length === 0) {
    return (
      <div className="lap-no-milestones">
        <p>No milestones available yet.</p>
      </div>
    );
  }

  const completedCount = milestones.filter((m) => m.status === 'completed').length;
  const progress = Math.round((completedCount / milestones.length) * 100);

  return (
    <div className="lap-milestone-timeline">
      <div className="lap-milestone-progress">
        <div className="lap-progress-bar">
          <div className="lap-progress-fill" style={{ width: `${progress}%` }}></div>
        </div>
        <span className="lap-progress-text">{progress}% Complete</span>
      </div>

      <div className="lap-milestones-list">
        {milestones.map((milestone, index) => (
          <div
            key={milestone.id || index}
            className={`lap-milestone-item ${milestone.status}`}
          >
            <div className="lap-milestone-icon">
              {getMilestoneStatusIcon(milestone.status)}
            </div>
            <div className="lap-milestone-content">
              <div className="lap-milestone-name">{milestone.milestone_name}</div>
              {milestone.description && (
                <div className="lap-milestone-desc">{milestone.description}</div>
              )}
              {milestone.completed_at && (
                <div className="lap-milestone-date">
                  Completed {formatDate(milestone.completed_at)}
                </div>
              )}
              {!milestone.completed_at && milestone.target_date && (
                <div className="lap-milestone-date">
                  Target: {formatDate(milestone.target_date)}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Message Thread Component
const MessageThread = ({ messages, onSendMessage, loading }) => {
  const [newMessage, setNewMessage] = useState('');
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!newMessage.trim() || sending) return;

    setSending(true);
    try {
      await onSendMessage(newMessage.trim());
      setNewMessage('');
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="lap-message-thread">
      <div className="lap-messages-container">
        {loading ? (
          <div className="lap-messages-loading">Loading messages...</div>
        ) : messages.length === 0 ? (
          <div className="lap-no-messages">
            <p>No messages yet. Send a message to your loan officer.</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`lap-message ${msg.sender_type === 'party' ? 'outgoing' : 'incoming'}`}
            >
              <div className="lap-message-header">
                <span className="lap-sender-name">{msg.sender_name}</span>
                <span className="lap-message-time">{formatDateTime(msg.created_at)}</span>
              </div>
              <div className="lap-message-content">{msg.content}</div>
            </div>
          ))
        )}
      </div>

      <div className="lap-message-composer">
        <textarea
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={2}
          disabled={sending}
        />
        <button
          className="lap-btn lap-btn-primary"
          onClick={handleSend}
          disabled={!newMessage.trim() || sending}
        >
          {sending ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  );
};

// Notification Settings Component
const NotificationSettings = ({ party, onUpdate }) => {
  const [settings, setSettings] = useState({
    notify_weekly_updates: party?.notify_weekly_updates ?? true,
    notify_milestone_changes: party?.notify_milestone_changes ?? true,
    notify_messages: party?.notify_messages ?? true,
  });
  const [saving, setSaving] = useState(false);

  const handleChange = (key) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdate(settings);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="lap-notification-settings">
      <h3>Notification Preferences</h3>

      <div className="lap-setting-item">
        <label>
          <input
            type="checkbox"
            checked={settings.notify_weekly_updates}
            onChange={() => handleChange('notify_weekly_updates')}
          />
          <span>Weekly Status Updates</span>
        </label>
        <p className="lap-setting-desc">Receive weekly summaries of loan progress</p>
      </div>

      <div className="lap-setting-item">
        <label>
          <input
            type="checkbox"
            checked={settings.notify_milestone_changes}
            onChange={() => handleChange('notify_milestone_changes')}
          />
          <span>Milestone Notifications</span>
        </label>
        <p className="lap-setting-desc">Get notified when milestones are completed</p>
      </div>

      <div className="lap-setting-item">
        <label>
          <input
            type="checkbox"
            checked={settings.notify_messages}
            onChange={() => handleChange('notify_messages')}
          />
          <span>Message Notifications</span>
        </label>
        <p className="lap-setting-desc">Receive notifications for new messages</p>
      </div>

      <button
        className="lap-btn lap-btn-primary"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? 'Saving...' : 'Save Preferences'}
      </button>
    </div>
  );
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function ListingAgentPortal() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // State
  const [authenticated, setAuthenticated] = useState(hasValidSession());
  const [sessionData, setSessionData] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [selectedTransaction, setSelectedTransaction] = useState(null);
  const [transactionDetail, setTransactionDetail] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('milestones');
  const [messagesLoading, setMessagesLoading] = useState(false);

  // Handle magic link authentication
  const handleAuthenticate = useCallback((response) => {
    setSessionData(response);
    setAuthenticated(true);
    // Clear token from URL
    navigate('/listing-agent-portal', { replace: true });
  }, [navigate]);

  // Fetch dashboard data
  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await dashboardApi.getDashboard();
      setDashboardData(data);

      // Select first active transaction by default
      if (data.active_transactions?.length > 0 && !selectedTransaction) {
        setSelectedTransaction(data.active_transactions[0]);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard:', err);
      if (err.message?.includes('401') || err.message?.includes('403')) {
        clearSessionToken();
        setAuthenticated(false);
      } else {
        setError(err);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedTransaction]);

  // Fetch transaction detail
  const fetchTransactionDetail = useCallback(async (transactionId) => {
    try {
      const detail = await transactionApi.getTransaction(transactionId);
      setTransactionDetail(detail);
    } catch (err) {
      console.error('Failed to fetch transaction detail:', err);
    }
  }, []);

  // Fetch messages
  const fetchMessages = useCallback(async (transactionId) => {
    try {
      setMessagesLoading(true);
      const response = await messagingApi.getMessages(transactionId);
      setMessages(response.messages || []);
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  // Send message
  const handleSendMessage = useCallback(async (content) => {
    if (!selectedTransaction) return;

    await messagingApi.sendMessage(selectedTransaction.id, content);
    await fetchMessages(selectedTransaction.id);
  }, [selectedTransaction, fetchMessages]);

  // Update notification preferences
  const handleUpdateNotifications = useCallback(async (settings) => {
    if (!transactionDetail?.transaction?.id || !sessionData?.party?.id) return;

    // This would call the party update API
    console.log('Updating notification settings:', settings);
  }, [transactionDetail, sessionData]);

  // Load dashboard on authentication
  useEffect(() => {
    if (authenticated) {
      fetchDashboard();
    }
  }, [authenticated, fetchDashboard]);

  // Load transaction detail when selected
  useEffect(() => {
    if (selectedTransaction?.id) {
      fetchTransactionDetail(selectedTransaction.id);
      if (activeTab === 'messages') {
        fetchMessages(selectedTransaction.id);
      }
    }
  }, [selectedTransaction, activeTab, fetchTransactionDetail, fetchMessages]);

  // Check for existing session on mount
  useEffect(() => {
    const token = searchParams.get('token');
    if (!token && hasValidSession()) {
      // Try to restore session
      authApi.getSession()
        .then((response) => {
          setSessionData(response);
          setAuthenticated(true);
        })
        .catch(() => {
          clearSessionToken();
          setAuthenticated(false);
        });
    }
  }, [searchParams]);

  // Handle tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab === 'messages' && selectedTransaction?.id) {
      fetchMessages(selectedTransaction.id);
    }
  };

  // Render authentication screen if not authenticated
  if (!authenticated) {
    return <MagicLinkAuth onAuthenticate={handleAuthenticate} />;
  }

  // Loading state
  if (loading) {
    return <LoadingSpinner />;
  }

  // Error state
  if (error) {
    return <ErrorDisplay error={error} onRetry={fetchDashboard} />;
  }

  // Get party info
  const partyInfo = sessionData?.party || transactionDetail?.parties?.find(
    (p) => p.role === 'listing_agent'
  );

  return (
    <div className="lap-container">
      {/* Header */}
      <header className="lap-header">
        <div className="lap-header-content">
          <div className="lap-logo">
            <span className="lap-logo-icon">🏠</span>
            <span className="lap-logo-text">Listing Agent Portal</span>
          </div>

          {partyInfo && (
            <div className="lap-user-info">
              <span className="lap-user-name">
                {partyInfo.first_name} {partyInfo.last_name}
              </span>
              <span className="lap-user-role">{partyInfo.role?.replace('_', ' ')}</span>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="lap-main">
        {/* Sidebar - Transaction List */}
        <aside className="lap-sidebar">
          <h2 className="lap-sidebar-title">Transactions</h2>

          <div className="lap-transactions-list">
            {dashboardData?.active_transactions?.map((transaction) => (
              <TransactionCard
                key={transaction.id}
                transaction={transaction}
                onClick={setSelectedTransaction}
                isSelected={selectedTransaction?.id === transaction.id}
              />
            ))}

            {(!dashboardData?.active_transactions ||
              dashboardData.active_transactions.length === 0) && (
              <div className="lap-no-transactions">
                <p>No active transactions</p>
              </div>
            )}
          </div>

          {dashboardData?.upcoming_closings?.length > 0 && (
            <div className="lap-upcoming-section">
              <h3>Upcoming Closings</h3>
              {dashboardData.upcoming_closings.slice(0, 3).map((transaction) => (
                <div
                  key={transaction.id}
                  className="lap-upcoming-item"
                  onClick={() => setSelectedTransaction(transaction)}
                >
                  <span className="lap-upcoming-address">{transaction.property_address}</span>
                  <span className="lap-upcoming-date">
                    {formatDate(transaction.target_close_date)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* Content Area */}
        <section className="lap-content">
          {selectedTransaction ? (
            <>
              {/* Transaction Header */}
              <div className="lap-transaction-header-large">
                <div className="lap-transaction-info">
                  <h1 className="lap-property-title">{selectedTransaction.property_address}</h1>
                  <div className="lap-property-location">
                    {selectedTransaction.property_city}, {selectedTransaction.property_state}{' '}
                    {selectedTransaction.property_zip}
                  </div>
                </div>

                <div className="lap-transaction-stats">
                  {selectedTransaction.purchase_price && (
                    <div className="lap-stat">
                      <span className="lap-stat-value">
                        {formatCurrency(selectedTransaction.purchase_price)}
                      </span>
                      <span className="lap-stat-label">Purchase Price</span>
                    </div>
                  )}

                  {selectedTransaction.target_close_date && (
                    <div className="lap-stat">
                      <span className="lap-stat-value">
                        {getDaysUntilClose(selectedTransaction.target_close_date)}
                      </span>
                      <span className="lap-stat-label">Days to Close</span>
                    </div>
                  )}

                  <div className="lap-stat">
                    <span
                      className="lap-stat-value lap-status"
                      style={{ color: getStatusColor(selectedTransaction.current_status) }}
                    >
                      {selectedTransaction.current_status}
                    </span>
                    <span className="lap-stat-label">Status</span>
                  </div>
                </div>
              </div>

              {/* Tabs */}
              <div className="lap-tabs">
                <button
                  className={`lap-tab ${activeTab === 'milestones' ? 'active' : ''}`}
                  onClick={() => handleTabChange('milestones')}
                >
                  Milestones
                </button>
                <button
                  className={`lap-tab ${activeTab === 'messages' ? 'active' : ''}`}
                  onClick={() => handleTabChange('messages')}
                >
                  Messages
                  {selectedTransaction.unread_messages > 0 && (
                    <span className="lap-tab-badge">{selectedTransaction.unread_messages}</span>
                  )}
                </button>
                <button
                  className={`lap-tab ${activeTab === 'settings' ? 'active' : ''}`}
                  onClick={() => handleTabChange('settings')}
                >
                  Settings
                </button>
              </div>

              {/* Tab Content */}
              <div className="lap-tab-content">
                {activeTab === 'milestones' && (
                  <MilestoneTimeline
                    milestones={
                      transactionDetail?.milestones || selectedTransaction.milestones || []
                    }
                  />
                )}

                {activeTab === 'messages' && (
                  <MessageThread
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    loading={messagesLoading}
                  />
                )}

                {activeTab === 'settings' && (
                  <NotificationSettings
                    party={partyInfo}
                    onUpdate={handleUpdateNotifications}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="lap-no-selection">
              <div className="lap-no-selection-icon">📋</div>
              <h2>Select a Transaction</h2>
              <p>Choose a transaction from the sidebar to view details.</p>
            </div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="lap-footer">
        <p>Powered by Perennia AI</p>
        <div className="lap-footer-links">
          <button onClick={() => setActiveTab('settings')}>Notification Settings</button>
          <span>|</span>
          <button
            onClick={() => {
              clearSessionToken();
              setAuthenticated(false);
            }}
          >
            Sign Out
          </button>
        </div>
      </footer>
    </div>
  );
}
