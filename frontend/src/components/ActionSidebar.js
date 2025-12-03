import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { commandCenterAPI, tasksAPI, reconciliationAPI } from '../services/api';
import './ActionSidebar.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

const ActionSidebar = ({ onTaskSelect, onClose }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('tasks');
  const [selectedItem, setSelectedItem] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [completingTask, setCompletingTask] = useState(false);

  // Call-related state
  const [selectedCallIds, setSelectedCallIds] = useState(new Set());
  const [powerDialing, setPowerDialing] = useState(false);
  const [currentCallIndex, setCurrentCallIndex] = useState(0);
  const [callInProgress, setCallInProgress] = useState(false);

  // Fetch command center data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const result = await commandCenterAPI.getAll();
      setData(result);
      setError(null);
    } catch (err) {
      console.error('Action sidebar error:', err);
      setError('Error loading action items');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 120000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Helper to check if an item is phone/call related
  const isPhoneTask = (item) => {
    const phoneTypes = ['follow_up', 'call', 'voicemail', 'sms', 'phone'];
    const phoneKeywords = ['call', 'phone', 'voicemail', 'sms', 'text', 'contact', 'follow up', 'follow-up'];
    if (phoneTypes.includes(item.type?.toLowerCase())) return true;
    const title = (item.title || '').toLowerCase();
    const desc = (item.description || '').toLowerCase();
    return phoneKeywords.some(keyword => title.includes(keyword) || desc.includes(keyword));
  };

  // Helper to check if an item is email related
  const isEmailTask = (item) => {
    const emailTypes = ['email', 'email_pending', 'reconciliation'];
    const emailKeywords = ['email', 'reconcil'];
    if (emailTypes.includes(item.type?.toLowerCase())) return true;
    const title = (item.title || '').toLowerCase();
    const desc = (item.description || '').toLowerCase();
    return emailKeywords.some(keyword => title.includes(keyword) || desc.includes(keyword));
  };

  // Get items for each tab
  const getTaskItems = () => {
    if (!data) return [];
    const items = [];
    if (data.urgent?.length) {
      items.push(...data.urgent.filter(item => !isPhoneTask(item) && !isEmailTask(item)).map(item => ({ ...item, category: 'urgent' })));
    }
    if (data.leads?.length) {
      items.push(...data.leads.filter(item => !isPhoneTask(item) && !isEmailTask(item)).map(item => ({ ...item, category: 'leads' })));
    }
    if (data.loans?.length) {
      items.push(...data.loans.filter(item => !isPhoneTask(item) && !isEmailTask(item)).map(item => ({ ...item, category: 'loans' })));
    }
    if (data.portfolio?.length) {
      items.push(...data.portfolio.filter(item => !isPhoneTask(item) && !isEmailTask(item)).map(item => ({ ...item, category: 'portfolio' })));
    }
    return items;
  };

  const getEmailItems = () => {
    if (!data) return [];
    const items = [];
    if (data.emails?.length) {
      items.push(...data.emails.map(item => ({ ...item, category: 'emails' })));
    }
    if (data.reconciliation?.length) {
      items.push(...data.reconciliation.map(item => ({ ...item, category: 'reconciliation' })));
    }
    if (data.urgent?.length) {
      items.push(...data.urgent.filter(isEmailTask).map(item => ({ ...item, category: 'urgent' })));
    }
    if (data.leads?.length) {
      items.push(...data.leads.filter(isEmailTask).map(item => ({ ...item, category: 'leads' })));
    }
    if (data.loans?.length) {
      items.push(...data.loans.filter(isEmailTask).map(item => ({ ...item, category: 'loans' })));
    }
    return items;
  };

  const getCallItems = () => {
    if (!data) return [];
    const items = [];
    if (data.calls?.length) {
      items.push(...data.calls.map(item => ({ ...item, category: 'calls' })));
    }
    if (data.sms?.length) {
      items.push(...data.sms.map(item => ({ ...item, category: 'sms' })));
    }
    if (data.urgent?.length) {
      items.push(...data.urgent.filter(isPhoneTask).map(item => ({ ...item, category: 'urgent' })));
    }
    if (data.leads?.length) {
      items.push(...data.leads.filter(isPhoneTask).map(item => ({ ...item, category: 'leads' })));
    }
    if (data.loans?.length) {
      items.push(...data.loans.filter(isPhoneTask).map(item => ({ ...item, category: 'loans' })));
    }
    if (data.portfolio?.length) {
      items.push(...data.portfolio.filter(isPhoneTask).map(item => ({ ...item, category: 'portfolio' })));
    }
    return items;
  };

  const getTabItems = () => {
    switch (activeTab) {
      case 'tasks': return getTaskItems();
      case 'emails': return getEmailItems();
      case 'calls': return getCallItems();
      default: return [];
    }
  };

  const getTabCount = (tab) => {
    switch (tab) {
      case 'tasks': return getTaskItems().length;
      case 'emails': return getEmailItems().length;
      case 'calls': return getCallItems().length;
      default: return 0;
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority?.toLowerCase()) {
      case 'critical': return '#ef4444';
      case 'high': return '#f97316';
      case 'medium': return '#eab308';
      case 'low': return '#22c55e';
      default: return '#9ca3af';
    }
  };

  const getTypeIcon = (type, category) => {
    if (category === 'urgent') return '🚨';
    if (category === 'reconciliation') return '🔄';
    if (category === 'calls' || category === 'sms') return '📞';
    if (category === 'emails') return '📧';
    if (category === 'portfolio') return '👋';
    switch (type) {
      case 'sla_alert': return '⚠️';
      case 'task': return '✅';
      case 'follow_up': return '📞';
      case 'lock_expiring': return '🔒';
      case 'closing_soon': return '🏠';
      case 'touchpoint': return '👋';
      case 'email_pending': return '📧';
      case 'sms_unanswered': return '💬';
      case 'voicemail': return '📱';
      default: return '📋';
    }
  };

  const getCategoryLabel = (category) => {
    const labels = {
      urgent: 'Urgent',
      leads: 'Lead',
      loans: 'Loan',
      portfolio: 'Portfolio',
      emails: 'Email',
      sms: 'SMS',
      calls: 'Call',
      reconciliation: 'Reconcile'
    };
    return labels[category] || category;
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    if (minutes < 60) return `${minutes}m`;
    if (hours < 24) return `${hours}h`;
    if (days < 7) return `${days}d`;
    return date.toLocaleDateString();
  };

  const handleItemClick = (item) => {
    setSelectedItem(selectedItem?.id === item.id ? null : item);
    if (onTaskSelect) {
      onTaskSelect(item);
    }
  };

  // Complete a task
  const handleCompleteTask = async (item) => {
    setCompletingTask(true);
    try {
      // Extract numeric ID from various formats
      let taskId = item.id;
      if (typeof taskId === 'string') {
        // Handle formats like 'task_123', 'workflow_123', 'deadline_123_active_loan'
        const match = taskId.match(/\d+/);
        if (match) {
          taskId = match[0];
        }
      }

      await tasksAPI.update(taskId, { status: 'completed' });

      // Remove from selected and refresh
      setSelectedItem(null);
      fetchData();
    } catch (err) {
      console.error('Complete task error:', err);
      alert('Failed to complete task. Please try again.');
    } finally {
      setCompletingTask(false);
    }
  };

  // Make a phone call
  const handleMakeCall = async (item) => {
    const phone = item.phone || item.entity_phone || item.borrower_phone;
    if (!phone) {
      alert('No phone number available for this contact');
      return;
    }

    setCallInProgress(true);
    try {
      // Call the dialer API to initiate call
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE}/api/v1/dialer/click-to-call`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          phone_number: phone,
          contact_name: item.entity_name || item.title,
          entity_type: item.entity_type,
          entity_id: item.entity_id
        })
      });

      if (response.ok) {
        // Mark task as completed after call initiated
        await handleCompleteTask(item);
      } else {
        const error = await response.json();
        alert(`Call failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Call error:', err);
      // Fallback to tel: link
      window.location.href = `tel:${phone}`;
      // Still mark as complete
      await handleCompleteTask(item);
    } finally {
      setCallInProgress(false);
    }
  };

  // Toggle call selection
  const handleToggleCallSelection = (itemId) => {
    setSelectedCallIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  // Select all calls
  const handleSelectAllCalls = () => {
    const callItems = getCallItems();
    if (selectedCallIds.size === callItems.length) {
      setSelectedCallIds(new Set());
    } else {
      setSelectedCallIds(new Set(callItems.map(item => item.id)));
    }
  };

  // Start power dialer
  const handleStartPowerDial = async () => {
    const callItems = getCallItems().filter(item => selectedCallIds.has(item.id));
    if (callItems.length === 0) {
      alert('Please select contacts to call');
      return;
    }

    setPowerDialing(true);
    setCurrentCallIndex(0);

    // Start calling the first contact
    await handleMakeCall(callItems[0]);
  };

  // Navigate to entity
  const handleNavigate = (item) => {
    if (item.url) {
      navigate(item.url);
    }
  };

  const items = getTabItems();
  const callItems = getCallItems();
  const allCallsSelected = callItems.length > 0 && selectedCallIds.size === callItems.length;

  return (
    <div className="action-sidebar">
      <div className="action-sidebar-header">
        <h2>Action Center</h2>
        <div className="header-actions">
          <button
            className={`refresh-btn ${refreshing ? 'refreshing' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh"
          >
            🔄
          </button>
          {onClose && (
            <button className="close-btn" onClick={onClose}>×</button>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="action-tabs">
        <button
          className={`action-tab ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => { setActiveTab('tasks'); setSelectedItem(null); }}
        >
          <span className="tab-icon">✅</span>
          <span className="tab-label">Tasks</span>
          {getTabCount('tasks') > 0 && (
            <span className="tab-count">{getTabCount('tasks')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'emails' ? 'active' : ''}`}
          onClick={() => { setActiveTab('emails'); setSelectedItem(null); }}
        >
          <span className="tab-icon">📧</span>
          <span className="tab-label">Emails</span>
          {getTabCount('emails') > 0 && (
            <span className="tab-count">{getTabCount('emails')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'calls' ? 'active' : ''}`}
          onClick={() => { setActiveTab('calls'); setSelectedItem(null); }}
        >
          <span className="tab-icon">📞</span>
          <span className="tab-label">Calls</span>
          {getTabCount('calls') > 0 && (
            <span className="tab-count">{getTabCount('calls')}</span>
          )}
        </button>
      </div>

      {/* Power Dialer Controls (Calls tab only) */}
      {activeTab === 'calls' && items.length > 0 && (
        <div className="power-dialer-controls">
          <label className="select-all-label">
            <input
              type="checkbox"
              checked={allCallsSelected}
              onChange={handleSelectAllCalls}
            />
            Select All ({callItems.length})
          </label>
          <button
            className="power-dial-btn"
            onClick={handleStartPowerDial}
            disabled={selectedCallIds.size === 0 || powerDialing}
          >
            {powerDialing ? '📞 Dialing...' : `📞 Power Dial (${selectedCallIds.size})`}
          </button>
        </div>
      )}

      {/* Content Area - Split View */}
      <div className={`action-content ${selectedItem ? 'with-detail' : ''}`}>
        {loading ? (
          <div className="action-loading">
            <div className="loading-spinner"></div>
            <p>Loading...</p>
          </div>
        ) : error ? (
          <div className="action-error">
            <p>{error}</p>
            <button onClick={handleRefresh}>Retry</button>
          </div>
        ) : items.length === 0 ? (
          <div className="action-empty">
            <span className="empty-icon">
              {activeTab === 'tasks' ? '✅' : activeTab === 'emails' ? '📧' : '📞'}
            </span>
            <p>No {activeTab} to complete</p>
            <span className="empty-subtext">You're all caught up!</span>
          </div>
        ) : (
          <>
            {/* Item List */}
            <div className="action-list">
              {items.map((item, idx) => (
                <div
                  key={item.id || idx}
                  className={`action-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.priority === 'critical' ? 'critical' : ''} ${activeTab === 'calls' ? 'with-checkbox' : ''}`}
                  onClick={() => handleItemClick(item)}
                >
                  {activeTab === 'calls' && (
                    <div className="call-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedCallIds.has(item.id)}
                        onChange={(e) => {
                          e.stopPropagation();
                          handleToggleCallSelection(item.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                  )}
                  <div
                    className="priority-bar"
                    style={{ backgroundColor: getPriorityColor(item.priority) }}
                  />
                  <div className="item-content">
                    <div className="item-header">
                      <span className="item-icon">{getTypeIcon(item.type, item.category)}</span>
                      <span className="item-category">{getCategoryLabel(item.category)}</span>
                      {item.created_at && (
                        <span className="item-time">{formatTimeAgo(item.created_at)}</span>
                      )}
                    </div>
                    <div className="item-title">{item.title}</div>
                    {item.entity_name && (
                      <div className="item-entity">{item.entity_name}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail Panel */}
            {selectedItem && (
              <div className="action-detail-panel">
                <div className="detail-header">
                  <span className="detail-icon">{getTypeIcon(selectedItem.type, selectedItem.category)}</span>
                  <div className="detail-title-section">
                    <h3>{selectedItem.title}</h3>
                    <span className="detail-category">{getCategoryLabel(selectedItem.category)}</span>
                  </div>
                  <button className="detail-close" onClick={() => setSelectedItem(null)}>×</button>
                </div>

                <div className="detail-body">
                  {/* Entity Info */}
                  {selectedItem.entity_name && (
                    <div className="detail-field">
                      <label>Client</label>
                      <span className="detail-value client-name">{selectedItem.entity_name}</span>
                    </div>
                  )}

                  {/* Loan/Lead Info */}
                  {selectedItem.loan_number && (
                    <div className="detail-field">
                      <label>Loan #</label>
                      <span className="detail-value">{selectedItem.loan_number}</span>
                    </div>
                  )}

                  {/* Status */}
                  {selectedItem.status && (
                    <div className="detail-field">
                      <label>Status</label>
                      <span className="detail-value status-badge">{selectedItem.status}</span>
                    </div>
                  )}

                  {/* Due Date */}
                  {selectedItem.due_date && (
                    <div className="detail-field">
                      <label>Due</label>
                      <span className="detail-value">{new Date(selectedItem.due_date).toLocaleDateString()}</span>
                    </div>
                  )}

                  {/* Description / Message Body */}
                  {selectedItem.description && (
                    <div className="detail-field full-width">
                      <label>Details</label>
                      <div className="detail-message">{selectedItem.description}</div>
                    </div>
                  )}

                  {/* AI Message (if available) */}
                  {selectedItem.ai_message && (
                    <div className="detail-field full-width">
                      <label>AI Drafted Message</label>
                      <div className="detail-ai-message">{selectedItem.ai_message}</div>
                    </div>
                  )}

                  {/* Phone number for calls */}
                  {(selectedItem.phone || selectedItem.entity_phone || selectedItem.borrower_phone) && (
                    <div className="detail-field">
                      <label>Phone</label>
                      <span className="detail-value phone-number">
                        {selectedItem.phone || selectedItem.entity_phone || selectedItem.borrower_phone}
                      </span>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="detail-actions">
                  {activeTab === 'calls' ? (
                    <>
                      <button
                        className="detail-btn call-btn"
                        onClick={() => handleMakeCall(selectedItem)}
                        disabled={callInProgress}
                      >
                        {callInProgress ? '📞 Calling...' : '📞 Call & Complete'}
                      </button>
                      <button
                        className="detail-btn complete-btn"
                        onClick={() => handleCompleteTask(selectedItem)}
                        disabled={completingTask}
                      >
                        {completingTask ? '⏳ Completing...' : '✓ Mark Complete'}
                      </button>
                    </>
                  ) : activeTab === 'emails' ? (
                    <>
                      <button
                        className="detail-btn navigate-btn"
                        onClick={() => handleNavigate(selectedItem)}
                      >
                        📧 Open in Reconciliation
                      </button>
                      <button
                        className="detail-btn complete-btn"
                        onClick={() => handleCompleteTask(selectedItem)}
                        disabled={completingTask}
                      >
                        {completingTask ? '⏳ Completing...' : '✓ Mark Complete'}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="detail-btn complete-btn primary"
                        onClick={() => handleCompleteTask(selectedItem)}
                        disabled={completingTask}
                      >
                        {completingTask ? '⏳ Completing...' : '✓ Complete Task'}
                      </button>
                      {selectedItem.url && (
                        <button
                          className="detail-btn navigate-btn"
                          onClick={() => handleNavigate(selectedItem)}
                        >
                          → Open Details
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Summary Footer */}
      {data?.summary && (
        <div className="action-footer">
          <span className="total-count">
            {data.summary.total_action_items || 0} total items
          </span>
        </div>
      )}
    </div>
  );
};

export default ActionSidebar;
