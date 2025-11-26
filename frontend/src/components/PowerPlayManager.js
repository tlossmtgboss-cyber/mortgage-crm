import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './PowerPlayManager.css';

function PowerPlayManager() {
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [rateLockData, setRateLockData] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [message, setMessage] = useState({ type: '', text: '' });
  const [runningTouches, setRunningTouches] = useState(false);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const [powerPlayRes, rateLockRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/power-play/dashboard`, {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        }),
        fetch(`${API_BASE_URL}/api/v1/rate-lock/dashboard`, {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        })
      ]);

      if (powerPlayRes.ok) {
        const data = await powerPlayRes.json();
        setDashboardData(data);
      }

      if (rateLockRes.ok) {
        const data = await rateLockRes.json();
        setRateLockData(data);
      }
    } catch (error) {
      console.error('Error loading Power Play data:', error);
      setMessage({ type: 'error', text: 'Failed to load workflow data' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const handleRunScheduledTouches = async () => {
    setRunningTouches(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/power-play/run-scheduled-touches`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      });

      if (response.ok) {
        const data = await response.json();
        setMessage({
          type: 'success',
          text: `Processed ${data.touches_processed} scheduled touches`
        });
        loadDashboardData();
      } else {
        setMessage({ type: 'error', text: 'Failed to run scheduled touches' });
      }
    } catch (error) {
      console.error('Error running touches:', error);
      setMessage({ type: 'error', text: 'Error running scheduled touches' });
    } finally {
      setRunningTouches(false);
      setTimeout(() => setMessage({ type: '', text: '' }), 5000);
    }
  };

  const handleTriggerPowerPlay = async (entityType, entityId, trigger) => {
    try {
      const endpoint = entityType === 'lead'
        ? `${API_BASE_URL}/api/v1/leads/${entityId}/power-play`
        : `${API_BASE_URL}/api/v1/loans/${entityId}/power-play`;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ trigger })
      });

      if (response.ok) {
        const data = await response.json();
        setMessage({
          type: 'success',
          text: `${data.workflow_type}: ${data.actions_count} actions triggered`
        });
        loadDashboardData();
      } else {
        setMessage({ type: 'error', text: 'Failed to trigger Power Play' });
      }
    } catch (error) {
      console.error('Error triggering Power Play:', error);
      setMessage({ type: 'error', text: 'Error triggering Power Play' });
    }
    setTimeout(() => setMessage({ type: '', text: '' }), 5000);
  };

  const powerPlays = [
    {
      key: 'prospect',
      name: 'Prospect Power Play',
      description: 'Active buyers with timeline-based touches',
      color: '#3b82f6',
      icon: '🎯',
      touchFrequency: 'Platinum: 7d | Gold: 14d | Silver: 21d'
    },
    {
      key: 'prequal',
      name: 'PreQual Power Play',
      description: 'Soft-pulled, document collection focus',
      color: '#10b981',
      icon: '📋',
      touchFrequency: 'Every 3 days until pre-approval'
    },
    {
      key: 'pre_approved',
      name: 'Pre-Approved Power Play',
      description: 'House hunting, rate lock ready',
      color: '#8b5cf6',
      icon: '🏠',
      touchFrequency: 'Weekly until under contract'
    },
    {
      key: 'long_term_nurture',
      name: 'Long-Term Nurture',
      description: '10+ month buyers, passive engagement',
      color: '#f59e0b',
      icon: '📅',
      touchFrequency: 'Monthly touches'
    },
    {
      key: 'under_contract',
      name: 'Under Contract Power Play',
      description: 'Active loan management with rate lock',
      color: '#ef4444',
      icon: '📝',
      touchFrequency: 'Milestone-driven'
    }
  ];

  if (loading) {
    return (
      <div className="power-play-manager">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading Power Play workflows...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="power-play-manager">
      <div className="manager-header">
        <div className="header-content">
          <h2>Power Play Workflows</h2>
          <p>Automated engagement workflows for leads and loans</p>
        </div>
        <button
          className="run-touches-btn"
          onClick={handleRunScheduledTouches}
          disabled={runningTouches}
        >
          {runningTouches ? 'Running...' : 'Run Scheduled Touches'}
        </button>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="tab-navigation">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'rate-lock' ? 'active' : ''}
          onClick={() => setActiveTab('rate-lock')}
        >
          Rate Lock Intelligence
        </button>
        <button
          className={activeTab === 'touches' ? 'active' : ''}
          onClick={() => setActiveTab('touches')}
        >
          Due Touches
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="tab-content">
          {/* Summary Stats */}
          <div className="summary-stats">
            {dashboardData?.workflow_summary && (
              <>
                <div className="stat-card prospect">
                  <span className="stat-icon">🎯</span>
                  <span className="stat-value">{dashboardData.workflow_summary.prospect_count}</span>
                  <span className="stat-label">Prospects</span>
                </div>
                <div className="stat-card prequal">
                  <span className="stat-icon">📋</span>
                  <span className="stat-value">{dashboardData.workflow_summary.prequal_count}</span>
                  <span className="stat-label">PreQual</span>
                </div>
                <div className="stat-card pre-approved">
                  <span className="stat-icon">🏠</span>
                  <span className="stat-value">{dashboardData.workflow_summary.pre_approved_count}</span>
                  <span className="stat-label">Pre-Approved</span>
                </div>
                <div className="stat-card nurture">
                  <span className="stat-icon">📅</span>
                  <span className="stat-value">{dashboardData.workflow_summary.long_term_nurture_count}</span>
                  <span className="stat-label">Long-Term</span>
                </div>
                <div className="stat-card under-contract">
                  <span className="stat-icon">📝</span>
                  <span className="stat-value">{dashboardData.workflow_summary.under_contract_count}</span>
                  <span className="stat-label">Under Contract</span>
                </div>
              </>
            )}
          </div>

          {/* Power Play Cards */}
          <div className="power-play-grid">
            {powerPlays.map(pp => {
              const count = dashboardData?.workflow_summary?.[`${pp.key}_count`] || 0;
              const items = dashboardData?.workflows?.[pp.key] || [];

              return (
                <div key={pp.key} className="power-play-card" style={{ '--pp-color': pp.color }}>
                  <div className="pp-header">
                    <span className="pp-icon">{pp.icon}</span>
                    <div className="pp-title">
                      <h3>{pp.name}</h3>
                      <span className="pp-count">{count} active</span>
                    </div>
                  </div>
                  <p className="pp-description">{pp.description}</p>
                  <div className="pp-frequency">
                    <small>{pp.touchFrequency}</small>
                  </div>

                  {items.length > 0 && (
                    <div className="pp-items">
                      {items.slice(0, 5).map(item => (
                        <div key={item.id} className="pp-item">
                          <span className="item-name">{item.name || item.borrower_name}</span>
                          <span className="item-stage">{item.stage}</span>
                          {pp.key !== 'under_contract' && (
                            <button
                              className="trigger-btn"
                              onClick={() => handleTriggerPowerPlay('lead', item.id, 'manual')}
                              title="Trigger Power Play"
                            >
                              ▶
                            </button>
                          )}
                          {pp.key === 'under_contract' && (
                            <button
                              className="trigger-btn"
                              onClick={() => handleTriggerPowerPlay('loan', item.id, 'manual')}
                              title="Trigger Power Play"
                            >
                              ▶
                            </button>
                          )}
                        </div>
                      ))}
                      {items.length > 5 && (
                        <div className="pp-more">+{items.length - 5} more</div>
                      )}
                    </div>
                  )}

                  {items.length === 0 && (
                    <div className="pp-empty">No active items</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Rate Lock Intelligence Tab */}
      {activeTab === 'rate-lock' && (
        <div className="tab-content">
          <div className="rate-lock-section">
            <h3>Rate Lock Dashboard</h3>

            {rateLockData && (
              <>
                {/* Status Summary */}
                <div className="rate-lock-summary">
                  <div className="rl-stat">
                    <span className="rl-value">{rateLockData.total_loans || 0}</span>
                    <span className="rl-label">Total Loans</span>
                  </div>
                  <div className="rl-stat locked">
                    <span className="rl-value">{rateLockData.status_summary?.locked || 0}</span>
                    <span className="rl-label">Locked</span>
                  </div>
                  <div className="rl-stat floating">
                    <span className="rl-value">{rateLockData.status_summary?.float_monitoring || 0}</span>
                    <span className="rl-label">Float Monitoring</span>
                  </div>
                  <div className="rl-stat eligible">
                    <span className="rl-value">{rateLockData.status_summary?.eligible_no_lock || 0}</span>
                    <span className="rl-label">Eligible (No Lock)</span>
                  </div>
                  <div className="rl-stat expiring">
                    <span className="rl-value">{rateLockData.status_summary?.lock_expiring || 0}</span>
                    <span className="rl-label">Expiring Soon</span>
                  </div>
                </div>

                {/* Attention Needed */}
                {rateLockData.attention_needed?.length > 0 && (
                  <div className="attention-section">
                    <h4>Attention Needed</h4>
                    <div className="attention-list">
                      {rateLockData.attention_needed.map((item, idx) => (
                        <div key={idx} className={`attention-item priority-${item.priority}`}>
                          <div className="attention-info">
                            <strong>{item.borrower_name}</strong>
                            <span className="loan-number">{item.loan_number}</span>
                          </div>
                          <div className="attention-issue">
                            <span className={`priority-badge ${item.priority}`}>
                              {item.priority}
                            </span>
                            <span className="issue-text">{item.issue}</span>
                          </div>
                          {item.days_until_expiration !== undefined && (
                            <span className="days-badge">
                              {item.days_until_expiration} days
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {rateLockData.attention_needed?.length === 0 && (
                  <div className="no-attention">
                    <span className="check-icon">✓</span>
                    <p>No rate locks require immediate attention</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Due Touches Tab */}
      {activeTab === 'touches' && (
        <div className="tab-content">
          <div className="touches-section">
            <h3>Scheduled Touches</h3>

            {/* Due Today */}
            <div className="touch-group">
              <h4>Due Today</h4>
              {dashboardData?.touches_due?.today?.length > 0 ? (
                <div className="touch-list">
                  {dashboardData.touches_due.today.map(item => (
                    <div key={item.id} className="touch-item urgent">
                      <div className="touch-info">
                        <strong>{item.name}</strong>
                        <span className="touch-stage">{item.stage}</span>
                      </div>
                      <button
                        className="touch-action-btn"
                        onClick={() => handleTriggerPowerPlay('lead', item.id, 'scheduled_touch')}
                      >
                        Execute Touch
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-touches">No touches due today</p>
              )}
            </div>

            {/* Due This Week */}
            <div className="touch-group">
              <h4>Due This Week</h4>
              {dashboardData?.touches_due?.this_week?.length > 0 ? (
                <div className="touch-list">
                  {dashboardData.touches_due.this_week.map(item => (
                    <div key={item.id} className="touch-item">
                      <div className="touch-info">
                        <strong>{item.name}</strong>
                        <span className="touch-stage">{item.stage}</span>
                      </div>
                      <button
                        className="touch-action-btn secondary"
                        onClick={() => handleTriggerPowerPlay('lead', item.id, 'scheduled_touch')}
                      >
                        Execute Touch
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-touches">No touches due this week</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Info Section */}
      <div className="power-play-info">
        <h4>About Power Play Workflows</h4>
        <div className="info-grid">
          <div className="info-item">
            <strong>Timeline-Based Touches</strong>
            <p>Platinum (&lt;3 mo): Every 7 days, Gold (4-6 mo): Every 14 days, Silver (7-9 mo): Every 21 days</p>
          </div>
          <div className="info-item">
            <strong>Rate Lock Intelligence</strong>
            <p>Automatic lock score calculation based on MBS prices, Treasury yields, and days to close</p>
          </div>
          <div className="info-item">
            <strong>Automated Actions</strong>
            <p>Tasks, emails, SMS, and alerts triggered automatically based on workflow stage</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PowerPlayManager;
