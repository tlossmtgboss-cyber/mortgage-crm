import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './CommandCenter.css';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

function CommandCenter() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [refreshing, setRefreshing] = useState(false);

  const fetchCommandCenter = useCallback(async () => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/command-center`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const result = await response.json();
        setData(result);
        setError(null);
      } else {
        setError('Failed to load command center data');
      }
    } catch (err) {
      console.error('Command center error:', err);
      setError('Error connecting to server');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchCommandCenter();
    // Auto-refresh every 2 minutes
    const interval = setInterval(fetchCommandCenter, 120000);
    return () => clearInterval(interval);
  }, [fetchCommandCenter]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchCommandCenter();
  };

  const handleItemClick = (item) => {
    if (item.url) {
      navigate(item.url);
    }
  };

  const getPriorityIcon = (priority) => {
    switch (priority) {
      case 'critical': return '🔴';
      case 'high': return '🟠';
      case 'medium': return '🟡';
      case 'low': return '🟢';
      default: return '⚪';
    }
  };

  const getTypeIcon = (type) => {
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
      case 'reconciliation': return '🔄';
      case 'ai_approval': return '🤖';
      default: return '📋';
    }
  };

  const getCategoryLabel = (category) => {
    const labels = {
      urgent: 'Urgent',
      leads: 'Leads',
      loans: 'Loans',
      portfolio: 'Portfolio',
      emails: 'Emails',
      sms: 'SMS',
      calls: 'Calls',
      reconciliation: 'Reconciliation',
      approvals: 'AI Approvals'
    };
    return labels[category] || category;
  };

  const getCategoryIcon = (category) => {
    const icons = {
      urgent: '🚨',
      leads: '👤',
      loans: '🏠',
      portfolio: '📊',
      emails: '📧',
      sms: '💬',
      calls: '📱',
      reconciliation: '🔄',
      approvals: '🤖'
    };
    return icons[category] || '📋';
  };

  const getAllItems = () => {
    if (!data) return [];

    const categories = ['urgent', 'leads', 'loans', 'portfolio', 'emails', 'sms', 'calls', 'reconciliation', 'approvals'];
    let allItems = [];

    categories.forEach(cat => {
      if (data[cat] && data[cat].length > 0) {
        data[cat].forEach(item => {
          allItems.push({ ...item, category: cat });
        });
      }
    });

    // Sort by priority
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
    allItems.sort((a, b) => (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3));

    return allItems;
  };

  const getFilteredItems = () => {
    if (activeCategory === 'all') {
      return getAllItems();
    }
    return data?.[activeCategory] || [];
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="command-center">
        <div className="command-center-loading">
          <div className="loading-spinner"></div>
          <p>Loading Command Center...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="command-center">
        <div className="command-center-error">
          <p>{error}</p>
          <button onClick={handleRefresh}>Retry</button>
        </div>
      </div>
    );
  }

  const categories = ['urgent', 'leads', 'loans', 'portfolio', 'emails', 'sms', 'calls', 'reconciliation', 'approvals'];
  const filteredItems = getFilteredItems();

  return (
    <div className="command-center">
      <div className="command-center-header">
        <div className="header-left">
          <h1>Command Center</h1>
          <span className="total-badge">
            {data?.summary?.total_action_items || 0} action items
          </span>
        </div>
        <div className="header-right">
          <button
            className={`refresh-btn ${refreshing ? 'refreshing' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        {data?.summary?.urgent_count > 0 && (
          <div className="summary-card urgent" onClick={() => setActiveCategory('urgent')}>
            <span className="card-icon">🚨</span>
            <span className="card-count">{data.summary.urgent_count}</span>
            <span className="card-label">Urgent</span>
          </div>
        )}
        <div className={`summary-card ${activeCategory === 'leads' ? 'active' : ''}`} onClick={() => setActiveCategory('leads')}>
          <span className="card-icon">👤</span>
          <span className="card-count">{data?.summary?.leads_count || 0}</span>
          <span className="card-label">Leads</span>
        </div>
        <div className={`summary-card ${activeCategory === 'loans' ? 'active' : ''}`} onClick={() => setActiveCategory('loans')}>
          <span className="card-icon">🏠</span>
          <span className="card-count">{data?.summary?.loans_count || 0}</span>
          <span className="card-label">Loans</span>
        </div>
        <div className={`summary-card ${activeCategory === 'portfolio' ? 'active' : ''}`} onClick={() => setActiveCategory('portfolio')}>
          <span className="card-icon">📊</span>
          <span className="card-count">{data?.summary?.portfolio_count || 0}</span>
          <span className="card-label">Portfolio</span>
        </div>
        <div className={`summary-card ${activeCategory === 'emails' ? 'active' : ''}`} onClick={() => setActiveCategory('emails')}>
          <span className="card-icon">📧</span>
          <span className="card-count">{data?.summary?.emails_count || 0}</span>
          <span className="card-label">Emails</span>
        </div>
        <div className={`summary-card ${activeCategory === 'sms' ? 'active' : ''}`} onClick={() => setActiveCategory('sms')}>
          <span className="card-icon">💬</span>
          <span className="card-count">{data?.summary?.sms_count || 0}</span>
          <span className="card-label">SMS</span>
        </div>
        <div className={`summary-card ${activeCategory === 'calls' ? 'active' : ''}`} onClick={() => setActiveCategory('calls')}>
          <span className="card-icon">📱</span>
          <span className="card-count">{data?.summary?.calls_count || 0}</span>
          <span className="card-label">Calls</span>
        </div>
        <div className={`summary-card ${activeCategory === 'reconciliation' ? 'active' : ''}`} onClick={() => setActiveCategory('reconciliation')}>
          <span className="card-icon">🔄</span>
          <span className="card-count">{data?.summary?.reconciliation_count || 0}</span>
          <span className="card-label">Reconcile</span>
        </div>
        <div className={`summary-card ${activeCategory === 'approvals' ? 'active' : ''}`} onClick={() => setActiveCategory('approvals')}>
          <span className="card-icon">🤖</span>
          <span className="card-count">{data?.summary?.approvals_count || 0}</span>
          <span className="card-label">AI Actions</span>
        </div>
      </div>

      {/* Category Filter */}
      <div className="category-filter">
        <button
          className={`filter-btn ${activeCategory === 'all' ? 'active' : ''}`}
          onClick={() => setActiveCategory('all')}
        >
          All ({data?.summary?.total_action_items || 0})
        </button>
        {categories.map(cat => {
          const count = data?.summary?.[`${cat}_count`] || 0;
          if (count === 0) return null;
          return (
            <button
              key={cat}
              className={`filter-btn ${activeCategory === cat ? 'active' : ''}`}
              onClick={() => setActiveCategory(cat)}
            >
              {getCategoryIcon(cat)} {getCategoryLabel(cat)} ({count})
            </button>
          );
        })}
      </div>

      {/* Action Items List */}
      <div className="action-items-container">
        {filteredItems.length === 0 ? (
          <div className="no-items">
            <span className="no-items-icon">✅</span>
            <p>No action items in this category</p>
          </div>
        ) : (
          <div className="action-items-list">
            {filteredItems.map((item, index) => (
              <div
                key={item.id || index}
                className={`action-item priority-${item.priority}`}
                onClick={() => handleItemClick(item)}
              >
                <div className="item-priority">
                  {getPriorityIcon(item.priority)}
                </div>
                <div className="item-type">
                  {getTypeIcon(item.type)}
                </div>
                <div className="item-content">
                  <div className="item-title">{item.title}</div>
                  <div className="item-description">
                    {item.description}
                    {item.entity_name && (
                      <span className="item-entity"> - {item.entity_name}</span>
                    )}
                  </div>
                  <div className="item-meta">
                    {item.category && activeCategory === 'all' && (
                      <span className="meta-category">{getCategoryLabel(item.category)}</span>
                    )}
                    {item.due_date && (
                      <span className="meta-due">Due: {new Date(item.due_date).toLocaleDateString()}</span>
                    )}
                    {item.hours_old !== undefined && (
                      <span className={`meta-age ${item.hours_old > 24 ? 'old' : ''}`}>
                        {item.hours_old < 1 ? 'Just now' : `${Math.round(item.hours_old)}h old`}
                      </span>
                    )}
                    {item.days_stale !== undefined && (
                      <span className={`meta-stale ${item.days_stale > 5 ? 'critical' : ''}`}>
                        {item.days_stale} days
                      </span>
                    )}
                    {item.loan_number && (
                      <span className="meta-loan">#{item.loan_number}</span>
                    )}
                  </div>
                </div>
                <div className="item-action">
                  <span className="action-arrow">→</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Actions Panel */}
      <div className="quick-actions-panel">
        <h3>Quick Actions</h3>
        <div className="quick-actions-grid">
          <button onClick={() => navigate('/leads')} className="quick-action-btn">
            <span>👤</span> View Leads
          </button>
          <button onClick={() => navigate('/loans')} className="quick-action-btn">
            <span>🏠</span> View Loans
          </button>
          <button onClick={() => navigate('/portfolio')} className="quick-action-btn">
            <span>📊</span> View Portfolio
          </button>
          <button onClick={() => navigate('/reconciliation')} className="quick-action-btn">
            <span>🔄</span> Reconciliation
          </button>
          <button onClick={() => navigate('/tasks')} className="quick-action-btn">
            <span>✅</span> All Tasks
          </button>
          <button onClick={() => navigate('/communication-intelligence')} className="quick-action-btn">
            <span>📧</span> Communications
          </button>
        </div>
      </div>
    </div>
  );
}

export default CommandCenter;
