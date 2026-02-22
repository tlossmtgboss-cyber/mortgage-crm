import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  authenticateMagicLink,
  validateSession,
  getPortalDashboard,
  getPortalMessages,
  sendPortalMessage,
  storePortalSession,
  clearPortalSession,
  hasPortalSession,
  formatCurrency,
  formatDate,
  getStatusInfo,
  getMilestoneStatusInfo,
} from '../services/listingPortalApi';
import './ListingAgentPortal.css';

const ListingAgentPortal = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const messagesEndRef = useRef(null);

  // Auth state
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authenticating, setAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Data state
  const [party, setParty] = useState(null);
  const [transaction, setTransaction] = useState(null);
  const [milestones, setMilestones] = useState([]);
  const [messages, setMessages] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // UI state
  const [activeView, setActiveView] = useState('dashboard');
  const [messageText, setMessageText] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [loading, setLoading] = useState(false);

  // Authenticate with magic link token
  const authenticate = useCallback(async (token) => {
    try {
      setAuthenticating(true);
      setAuthError(null);
      const response = await authenticateMagicLink(token);

      if (response.data?.session_token) {
        storePortalSession(response.data.session_token);
        setIsAuthenticated(true);
        setParty(response.data.party);
        setTransaction(response.data.transaction);
      } else {
        throw new Error('Invalid authentication response');
      }
    } catch (err) {
      console.error('Authentication failed:', err);
      setAuthError(err.message || 'Authentication failed');
      setIsAuthenticated(false);
    } finally {
      setAuthenticating(false);
    }
  }, []);

  // Check existing session
  const checkSession = useCallback(async () => {
    if (!hasPortalSession()) {
      setAuthenticating(false);
      return;
    }

    try {
      setAuthenticating(true);
      const response = await validateSession();

      if (response.data?.party) {
        setIsAuthenticated(true);
        setParty(response.data.party);
        setTransaction(response.data.transaction);
      } else {
        clearPortalSession();
      }
    } catch (err) {
      console.error('Session validation failed:', err);
      clearPortalSession();
    } finally {
      setAuthenticating(false);
    }
  }, []);

  // Initial auth check
  useEffect(() => {
    const token = searchParams.get('token');

    if (token) {
      // Authenticate with magic link token
      authenticate(token);
      // Remove token from URL for security
      navigate('/listing-agent-portal', { replace: true });
    } else {
      // Check existing session
      checkSession();
    }
  }, [searchParams, authenticate, checkSession, navigate]);

  // Fetch dashboard data
  const fetchDashboard = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      setLoading(true);
      const response = await getPortalDashboard();
      const data = response.data;

      setParty(data.party);
      setTransaction(data.transaction);
      setMilestones(data.milestones || []);
      setUnreadCount(data.unread_messages || 0);
      setMessages(data.recent_messages || []);
    } catch (err) {
      console.error('Failed to fetch dashboard:', err);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchDashboard();
    }
  }, [isAuthenticated, fetchDashboard]);

  // Fetch messages when viewing messages
  const fetchMessages = useCallback(async () => {
    try {
      const response = await getPortalMessages();
      setMessages(response.data?.messages || []);
      setUnreadCount(0);
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  }, []);

  useEffect(() => {
    if (activeView === 'messages' && isAuthenticated) {
      fetchMessages();
    }
  }, [activeView, isAuthenticated, fetchMessages]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Send message
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!messageText.trim()) return;

    try {
      setSendingMessage(true);
      await sendPortalMessage(messageText.trim());
      setMessageText('');
      fetchMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
      toast.error('Failed to send message. Please try again.');
    } finally {
      setSendingMessage(false);
    }
  };

  // Logout
  const handleLogout = () => {
    clearPortalSession();
    setIsAuthenticated(false);
    setParty(null);
    setTransaction(null);
  };

  // Loading state
  if (authenticating) {
    return (
      <div className="listing-agent-portal">
        <div className="auth-container">
          <div className="auth-card">
            <div className="spinner large"></div>
            <h2>Verifying access...</h2>
            <p>Please wait while we authenticate your session.</p>
          </div>
        </div>
      </div>
    );
  }

  // Auth error state
  if (authError) {
    return (
      <div className="listing-agent-portal">
        <div className="auth-container">
          <div className="auth-card error">
            <div className="error-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M15 9l-6 6M9 9l6 6" />
              </svg>
            </div>
            <h2>Access Denied</h2>
            <p>{authError}</p>
            <p className="help-text">
              Please check your email for a valid portal access link, or contact your loan officer
              for assistance.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Not authenticated state
  if (!isAuthenticated) {
    return (
      <div className="listing-agent-portal">
        <div className="auth-container">
          <div className="auth-card">
            <div className="portal-logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>
            <h2>Transaction Portal</h2>
            <p>
              This portal provides secure access to transaction updates for listing agents and other
              parties.
            </p>
            <p className="help-text">
              To access your portal, please use the link provided in your email invitation.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Authenticated - show portal
  const statusInfo = getStatusInfo(transaction?.current_status);
  const completedMilestones = milestones.filter((m) => m.status === 'completed').length;
  const progress = milestones.length > 0 ? (completedMilestones / milestones.length) * 100 : 0;

  return (
    <div className="listing-agent-portal authenticated">
      {/* Header */}
      <header className="portal-header">
        <div className="header-brand">
          <div className="brand-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <span>Transaction Portal</span>
        </div>

        <div className="header-user">
          <span className="user-name">{party?.name}</span>
          <button className="logout-btn" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </header>

      {/* Property Banner */}
      <div className="property-banner">
        <div className="property-info">
          <h1>{transaction?.property_address}</h1>
          <p>
            {[transaction?.property_city, transaction?.property_state]
              .filter(Boolean)
              .join(', ')}
          </p>
        </div>
        <span
          className="status-badge"
          style={{ backgroundColor: statusInfo.bg, color: statusInfo.color }}
        >
          {statusInfo.label}
        </span>
      </div>

      {/* Navigation */}
      <nav className="portal-nav">
        <button
          className={`nav-item ${activeView === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveView('dashboard')}
        >
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
          </svg>
          Dashboard
        </button>
        <button
          className={`nav-item ${activeView === 'milestones' ? 'active' : ''}`}
          onClick={() => setActiveView('milestones')}
        >
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          Milestones
        </button>
        <button
          className={`nav-item ${activeView === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveView('messages')}
        >
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"
              clipRule="evenodd"
            />
          </svg>
          Messages
          {unreadCount > 0 && <span className="nav-badge">{unreadCount}</span>}
        </button>
      </nav>

      {/* Content */}
      <main className="portal-content">
        {loading && activeView === 'dashboard' ? (
          <div className="loading-content">
            <div className="spinner"></div>
            <p>Loading...</p>
          </div>
        ) : (
          <>
            {/* Dashboard View */}
            {activeView === 'dashboard' && (
              <div className="dashboard-view">
                {/* Progress Card */}
                <div className="dashboard-card progress-card">
                  <h2>Transaction Progress</h2>
                  <div className="progress-visual">
                    <div className="progress-bar large">
                      <div className="progress-fill" style={{ width: `${progress}%` }}></div>
                    </div>
                    <span className="progress-percentage">{Math.round(progress)}%</span>
                  </div>
                  <p className="progress-detail">
                    {completedMilestones} of {milestones.length} milestones completed
                  </p>
                </div>

                {/* Quick Stats */}
                <div className="stats-grid">
                  {transaction?.purchase_price && (
                    <div className="stat-card">
                      <span className="stat-label">Purchase Price</span>
                      <span className="stat-value">{formatCurrency(transaction.purchase_price)}</span>
                    </div>
                  )}
                  {transaction?.target_close_date && (
                    <div className="stat-card">
                      <span className="stat-label">Target Close Date</span>
                      <span className="stat-value">{formatDate(transaction.target_close_date)}</span>
                    </div>
                  )}
                </div>

                {/* Recent Milestones */}
                <div className="dashboard-card">
                  <div className="card-header">
                    <h2>Recent Milestones</h2>
                    <button className="link-btn" onClick={() => setActiveView('milestones')}>
                      View All
                    </button>
                  </div>
                  {milestones.length === 0 ? (
                    <p className="empty-text">No milestones available yet.</p>
                  ) : (
                    <ul className="milestone-list compact">
                      {milestones.slice(0, 4).map((milestone) => {
                        const msStatus = getMilestoneStatusInfo(milestone.status);
                        return (
                          <li key={milestone.id} className={`milestone-${milestone.status}`}>
                            <span className="milestone-indicator" style={{ color: msStatus.color }}>
                              {msStatus.icon}
                            </span>
                            <span className="milestone-name">{milestone.milestone_name}</span>
                            <span className="milestone-status" style={{ color: msStatus.color }}>
                              {msStatus.label}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>

                {/* Recent Messages Preview */}
                {messages.length > 0 && (
                  <div className="dashboard-card">
                    <div className="card-header">
                      <h2>Recent Messages</h2>
                      <button className="link-btn" onClick={() => setActiveView('messages')}>
                        View All
                      </button>
                    </div>
                    <ul className="message-preview-list">
                      {messages.slice(0, 2).map((msg) => (
                        <li key={msg.id}>
                          <span className="msg-sender">{msg.sender_name}</span>
                          <span className="msg-preview">
                            {msg.content.length > 80 ? msg.content.slice(0, 80) + '...' : msg.content}
                          </span>
                          <span className="msg-time">{formatDate(msg.created_at)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Milestones View */}
            {activeView === 'milestones' && (
              <div className="milestones-view">
                <div className="view-header">
                  <h2>Transaction Milestones</h2>
                  <div className="progress-indicator">
                    <span>{completedMilestones}/{milestones.length} Complete</span>
                  </div>
                </div>

                {milestones.length === 0 ? (
                  <div className="empty-state">
                    <p>No milestones have been defined for this transaction yet.</p>
                  </div>
                ) : (
                  <div className="milestones-timeline">
                    {milestones.map((milestone, index) => {
                      const msStatus = getMilestoneStatusInfo(milestone.status);
                      const isCompleted = milestone.status === 'completed';

                      return (
                        <div key={milestone.id} className={`timeline-item ${milestone.status}`}>
                          <div className="timeline-connector">
                            <div
                              className="timeline-dot"
                              style={{
                                backgroundColor: isCompleted ? msStatus.color : 'white',
                                borderColor: msStatus.color,
                              }}
                            >
                              {isCompleted && (
                                <svg viewBox="0 0 20 20" fill="white">
                                  <path
                                    fillRule="evenodd"
                                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              )}
                            </div>
                            {index < milestones.length - 1 && (
                              <div
                                className="timeline-line"
                                style={{
                                  backgroundColor: isCompleted ? '#10b981' : '#e2e8f0',
                                }}
                              ></div>
                            )}
                          </div>

                          <div className="timeline-content">
                            <div className="timeline-header">
                              <h3>{milestone.milestone_name}</h3>
                              <span className="status-label" style={{ color: msStatus.color }}>
                                {msStatus.label}
                              </span>
                            </div>
                            {milestone.description && (
                              <p className="timeline-description">{milestone.description}</p>
                            )}
                            {(milestone.target_date || milestone.completed_at) && (
                              <div className="timeline-meta">
                                {milestone.target_date && !isCompleted && (
                                  <span>Target: {formatDate(milestone.target_date)}</span>
                                )}
                                {milestone.completed_at && (
                                  <span>Completed: {formatDate(milestone.completed_at)}</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Messages View */}
            {activeView === 'messages' && (
              <div className="messages-view">
                <div className="view-header">
                  <h2>Messages</h2>
                </div>

                <div className="messages-wrapper">
                  <div className="messages-list">
                    {messages.length === 0 ? (
                      <div className="empty-messages">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        <p>No messages yet</p>
                        <span>Start a conversation with your loan officer!</span>
                      </div>
                    ) : (
                      messages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`message-bubble ${
                            msg.sender_type === 'party' ? 'outgoing' : 'incoming'
                          }`}
                        >
                          <div className="message-meta">
                            <span className="sender">{msg.sender_name}</span>
                            <span className="time">{formatDate(msg.created_at)}</span>
                          </div>
                          <div className="message-body">{msg.content}</div>
                        </div>
                      ))
                    )}
                    <div ref={messagesEndRef} />
                  </div>

                  <form className="message-composer" onSubmit={handleSendMessage}>
                    <input
                      type="text"
                      value={messageText}
                      onChange={(e) => setMessageText(e.target.value)}
                      placeholder="Type your message..."
                      disabled={sendingMessage}
                    />
                    <button
                      type="submit"
                      disabled={sendingMessage || !messageText.trim()}
                    >
                      {sendingMessage ? (
                        <div className="spinner small"></div>
                      ) : (
                        <svg viewBox="0 0 20 20" fill="currentColor">
                          <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                        </svg>
                      )}
                    </button>
                  </form>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="portal-footer">
        <p>
          Secure transaction portal powered by Perennia AI
        </p>
      </footer>
    </div>
  );
};

export default ListingAgentPortal;
