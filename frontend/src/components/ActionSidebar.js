import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { commandCenterAPI, tasksAPI, reconciliationAPI } from '../services/api';
import './ActionSidebar.css';

const ActionSidebar = ({ onTaskSelect, onClose }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('tasks');
  const [selectedItem, setSelectedItem] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

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
    // Auto-refresh every 2 minutes
    const interval = setInterval(fetchData, 120000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Get items for each tab
  const getTaskItems = () => {
    if (!data) return [];
    const items = [];

    // Add urgent items
    if (data.urgent?.length) {
      items.push(...data.urgent.map(item => ({ ...item, category: 'urgent' })));
    }

    // Add lead tasks
    if (data.leads?.length) {
      items.push(...data.leads.map(item => ({ ...item, category: 'leads' })));
    }

    // Add loan tasks
    if (data.loans?.length) {
      items.push(...data.loans.map(item => ({ ...item, category: 'loans' })));
    }

    // Add portfolio touchpoints
    if (data.portfolio?.length) {
      items.push(...data.portfolio.map(item => ({ ...item, category: 'portfolio' })));
    }

    return items;
  };

  const getEmailItems = () => {
    if (!data) return [];
    const items = [];

    // Add email items
    if (data.emails?.length) {
      items.push(...data.emails.map(item => ({ ...item, category: 'emails' })));
    }

    // Add reconciliation items
    if (data.reconciliation?.length) {
      items.push(...data.reconciliation.map(item => ({ ...item, category: 'reconciliation' })));
    }

    return items;
  };

  const getCallItems = () => {
    if (!data) return [];
    const items = [];

    // Add call/voicemail items
    if (data.calls?.length) {
      items.push(...data.calls.map(item => ({ ...item, category: 'calls' })));
    }

    // Add SMS items
    if (data.sms?.length) {
      items.push(...data.sms.map(item => ({ ...item, category: 'sms' })));
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
    setSelectedItem(item);
    if (onTaskSelect) {
      onTaskSelect(item);
    }
  };

  const handleItemAction = async (item, action) => {
    try {
      if (action === 'complete' && item.type === 'task') {
        // Extract task ID from the item id (format: task_123)
        const taskId = item.id.replace('task_', '');
        await tasksAPI.update(parseInt(taskId), { status: 'completed' });
      } else if (action === 'dismiss' && item.category === 'reconciliation') {
        const itemId = item.id.replace('reconciliation_', '');
        await reconciliationAPI.delete(parseInt(itemId));
      }
      // Refresh data after action
      fetchData();
    } catch (err) {
      console.error('Action error:', err);
    }
  };

  const handleNavigate = (item) => {
    if (item.url) {
      navigate(item.url);
    }
  };

  const items = getTabItems();

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
          onClick={() => setActiveTab('tasks')}
        >
          <span className="tab-icon">✅</span>
          <span className="tab-label">Tasks</span>
          {getTabCount('tasks') > 0 && (
            <span className="tab-count">{getTabCount('tasks')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'emails' ? 'active' : ''}`}
          onClick={() => setActiveTab('emails')}
        >
          <span className="tab-icon">📧</span>
          <span className="tab-label">Emails</span>
          {getTabCount('emails') > 0 && (
            <span className="tab-count">{getTabCount('emails')}</span>
          )}
        </button>
        <button
          className={`action-tab ${activeTab === 'calls' ? 'active' : ''}`}
          onClick={() => setActiveTab('calls')}
        >
          <span className="tab-icon">📞</span>
          <span className="tab-label">Calls</span>
          {getTabCount('calls') > 0 && (
            <span className="tab-count">{getTabCount('calls')}</span>
          )}
        </button>
      </div>

      {/* Content Area */}
      <div className="action-content">
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
          <div className="action-list">
            {items.map((item, idx) => (
              <div
                key={item.id || idx}
                className={`action-item ${selectedItem?.id === item.id ? 'selected' : ''} ${item.priority === 'critical' ? 'critical' : ''}`}
                onClick={() => handleItemClick(item)}
              >
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
                  {item.description && (
                    <div className="item-description">{item.description}</div>
                  )}
                  <div className="item-actions">
                    {item.type === 'task' && (
                      <button
                        className="action-btn complete"
                        onClick={(e) => { e.stopPropagation(); handleItemAction(item, 'complete'); }}
                      >
                        ✓ Complete
                      </button>
                    )}
                    {item.category === 'reconciliation' && (
                      <button
                        className="action-btn dismiss"
                        onClick={(e) => { e.stopPropagation(); handleItemAction(item, 'dismiss'); }}
                      >
                        ✗ Dismiss
                      </button>
                    )}
                    {item.url && (
                      <button
                        className="action-btn navigate"
                        onClick={(e) => { e.stopPropagation(); handleNavigate(item); }}
                      >
                        → Open
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
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
