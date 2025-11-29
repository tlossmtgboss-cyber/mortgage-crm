import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './SLASettings.css';

const SLASettings = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dashboard data
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [measures, setMeasures] = useState([]);
  const [trend, setTrend] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [runRates, setRunRates] = useState(null);

  // Modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingMeasure, setEditingMeasure] = useState(null);

  // Reports state
  const [teamMembers, setTeamMembers] = useState([]);
  const [reportHistory, setReportHistory] = useState([]);
  const [sendingReport, setSendingReport] = useState(false);

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Fetch dashboard summary
      const summaryRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/summary`, { headers });
      if (summaryRes.ok) {
        const summaryData = await summaryRes.json();
        setSummary(summaryData);
      }

      // Fetch alerts
      const alertsRes = await fetch(`${API_BASE_URL}/api/v1/sla/alerts?limit=10`, { headers });
      if (alertsRes.ok) {
        const alertsData = await alertsRes.json();
        setAlerts(alertsData);
      }

      // Fetch measures (including inactive ones so they can be reactivated)
      const measuresRes = await fetch(`${API_BASE_URL}/api/v1/sla/measures?active_only=false`, { headers });
      if (measuresRes.ok) {
        const measuresData = await measuresRes.json();
        setMeasures(measuresData);
      }

      // Fetch trend data
      const trendRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/trend`, { headers });
      if (trendRes.ok) {
        const trendData = await trendRes.json();
        setTrend(trendData.data_points || []);
      }

      // Fetch bottlenecks
      const bottlenecksRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/bottlenecks`, { headers });
      if (bottlenecksRes.ok) {
        const bottlenecksData = await bottlenecksRes.json();
        setBottlenecks(bottlenecksData.bottlenecks || []);
      }

      // Fetch run rates
      const runRatesRes = await fetch(`${API_BASE_URL}/api/v1/sla/dashboard/run-rates`, { headers });
      if (runRatesRes.ok) {
        const runRatesData = await runRatesRes.json();
        setRunRates(runRatesData);
      }

      // Fetch team members for reports
      try {
        const usersRes = await fetch(`${API_BASE_URL}/api/v1/users`, { headers });
        if (usersRes.ok) {
          const usersData = await usersRes.json();
          setTeamMembers(usersData.users || usersData || []);
        }
      } catch (e) {
        // Users endpoint might not exist, use empty array
        setTeamMembers([]);
      }

      setError(null);
    } catch (err) {
      setError('Failed to load SLA data');
      console.error('Error fetching SLA data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const runMigration = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/migrate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        alert('SLA tables created and default measures seeded!');
        fetchDashboard();
      }
    } catch (err) {
      console.error('Migration error:', err);
    }
  };

  const acknowledgeAlert = async (alertId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  };

  const resolveAlert = async (alertId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/alerts/${alertId}/resolve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ resolution_notes: 'Resolved from dashboard' })
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error resolving alert:', err);
    }
  };

  const saveMeasure = async (measureData) => {
    try {
      const token = localStorage.getItem('token');
      const method = editingMeasure ? 'PUT' : 'POST';
      const url = editingMeasure
        ? `${API_BASE_URL}/api/v1/sla/measures/${editingMeasure.id}`
        : `${API_BASE_URL}/api/v1/sla/measures`;

      await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(measureData)
      });
      setShowEditModal(false);
      setEditingMeasure(null);
      fetchDashboard();
    } catch (err) {
      console.error('Error saving measure:', err);
    }
  };

  const toggleMeasureActive = async (measureId, newActiveState) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measureId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ is_active: newActiveState })
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error toggling measure active state:', err);
    }
  };

  const deleteMeasure = async (measureId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/sla/measures/${measureId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      fetchDashboard();
    } catch (err) {
      console.error('Error deleting measure:', err);
    }
  };

  const sendReport = async (emailAddress, options = {}) => {
    try {
      setSendingReport(true);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/sla/reports/send-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email_address: emailAddress,
          include_run_rates: options.includeRunRates !== false,
          include_forecasts: options.includeForecasts !== false,
          include_bottlenecks: options.includeBottlenecks !== false
        })
      });

      if (response.ok) {
        const result = await response.json();
        // Add to history
        setReportHistory(prev => [{
          id: Date.now(),
          email: emailAddress,
          sentAt: new Date().toISOString(),
          status: 'sent',
          summary: result.report_summary
        }, ...prev.slice(0, 9)]);
        return { success: true, message: `Report sent to ${emailAddress}` };
      } else {
        const error = await response.json();
        return { success: false, message: error.detail || 'Failed to send report' };
      }
    } catch (err) {
      console.error('Error sending report:', err);
      return { success: false, message: 'Failed to send report' };
    } finally {
      setSendingReport(false);
    }
  };

  const formatMilestoneType = (type) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Define milestone stages for sorting - Lead stage first, then Loan stage
  const leadStageMilestones = [
    'lead_response', 'initial_consultation', 'lead_created', 'pre_qualified', 'preapproval'
  ];

  const loanStageMilestones = [
    'application_submitted', 'documents_requested', 'documents_received',
    'document_collection', 'application_complete',
    'submitted_to_processing', 'processing_start',
    'appraisal_ordered', 'appraisal_received',
    'title_ordered', 'title_received',
    'insurance_ordered', 'insurance_received',
    'submitted_to_uw', 'uw_decision', 'approved',
    'conditions_issued', 'conditions_cleared', 'clear_to_close',
    'closing_docs_out', 'closing_scheduled', 'closed', 'funded', 'loan_funded'
  ];

  // Get stage category for a milestone type
  const getMilestoneStage = (milestoneType) => {
    if (leadStageMilestones.includes(milestoneType)) return 'lead';
    if (loanStageMilestones.includes(milestoneType)) return 'loan';
    return 'other';
  };

  // Get sort order for a milestone within its stage
  const getMilestoneOrder = (milestoneType) => {
    const leadIndex = leadStageMilestones.indexOf(milestoneType);
    if (leadIndex !== -1) return leadIndex;
    const loanIndex = loanStageMilestones.indexOf(milestoneType);
    if (loanIndex !== -1) return loanIndex;
    return 999;
  };

  // Sort measures: Lead stage first, then Loan stage, then by status (Active first), then by order within stage
  const sortedMeasures = [...measures].sort((a, b) => {
    // First sort by stage (Lead = 0, Loan = 1, Other = 2)
    const stageOrder = { lead: 0, loan: 1, other: 2 };
    const stageA = stageOrder[getMilestoneStage(a.milestone_type)];
    const stageB = stageOrder[getMilestoneStage(b.milestone_type)];
    if (stageA !== stageB) return stageA - stageB;

    // Then sort by active status (Active first)
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;

    // Then sort by order within stage
    return getMilestoneOrder(a.milestone_type) - getMilestoneOrder(b.milestone_type);
  });

  // Group measures by stage for display
  const groupedMeasures = {
    lead: sortedMeasures.filter(m => getMilestoneStage(m.milestone_type) === 'lead'),
    loan: sortedMeasures.filter(m => getMilestoneStage(m.milestone_type) === 'loan'),
    other: sortedMeasures.filter(m => getMilestoneStage(m.milestone_type) === 'other')
  };

  // Render a single measure row
  const renderMeasureRow = (measure) => (
    <tr key={measure.id}>
      <td>
        <div className="milestone-name">{measure.name}</div>
        <div className="milestone-type">{formatMilestoneType(measure.milestone_type)}</div>
      </td>
      <td>
        <span className="target-badge">
          {formatTargetUnit(measure.target_value, measure.target_unit)}
        </span>
      </td>
      <td>
        <span style={{ fontSize: '13px', color: '#4b5563' }}>
          {formatMilestoneType(measure.trigger_from || 'previous_milestone')}
          {measure.trigger_from_is_default && (
            <span style={{
              marginLeft: '6px',
              fontSize: '10px',
              padding: '2px 6px',
              background: '#dbeafe',
              color: '#1d4ed8',
              borderRadius: '10px'
            }}>
              Default
            </span>
          )}
        </span>
      </td>
      <td>{measure.warning_threshold_pct}%</td>
      <td>
        <div className={`status-indicator ${measure.is_active ? 'active' : 'inactive'}`}>
          <span className="dot"></span>
          {measure.is_active ? 'Active' : 'Inactive'}
        </div>
      </td>
      <td>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <button
            onClick={() => {
              setEditingMeasure(measure);
              setShowEditModal(true);
            }}
            style={{
              padding: '6px 12px',
              background: '#f3f4f6',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            Edit
          </button>
          <button
            onClick={() => toggleMeasureActive(measure.id, !measure.is_active)}
            style={{
              padding: '6px 12px',
              background: measure.is_active ? '#fef3c7' : '#d1fae5',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              color: measure.is_active ? '#92400e' : '#065f46'
            }}
            title={measure.is_active ? 'Deactivate this measure' : 'Activate this measure'}
          >
            {measure.is_active ? 'Deactivate' : 'Activate'}
          </button>
          <button
            onClick={() => {
              if (window.confirm(`Are you sure you want to delete "${measure.name}"? This action cannot be undone.`)) {
                deleteMeasure(measure.id);
              }
            }}
            style={{
              padding: '6px 12px',
              background: '#fee2e2',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              color: '#991b1b'
            }}
            title="Delete this measure"
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  );

  const formatTargetUnit = (value, unit) => {
    const absValue = Math.abs(value);
    const unitLabel = unit === 'hours' ? 'hours' : unit === 'days' ? 'days' : 'business days';

    if (value < 0) {
      return `${absValue} ${unitLabel} before`;
    }
    return `${absValue} ${unitLabel}`;
  };

  if (loading) {
    return (
      <div className="sla-settings-page">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <span>Loading SLA data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="sla-settings-page">
      <div className="page-header">
        <h1>SLA Tracking</h1>
        <p>Monitor loan lifecycle milestones and service level agreements</p>
      </div>

      {/* Dashboard Summary */}
      <div className="sla-dashboard-summary">
        <div className="summary-card on-track">
          <div className="card-label">On Track</div>
          <div className="card-value">{summary?.on_track_count || 0}</div>
          <div className="card-sub">milestones within SLA</div>
        </div>
        <div className="summary-card at-risk">
          <div className="card-label">At Risk</div>
          <div className="card-value">{summary?.at_risk_count || 0}</div>
          <div className="card-sub">approaching deadline</div>
        </div>
        <div className="summary-card overdue">
          <div className="card-label">Overdue</div>
          <div className="card-value">{summary?.overdue_count || 0}</div>
          <div className="card-sub">past deadline</div>
        </div>
        <div className="summary-card alerts">
          <div className="card-label">Health Score</div>
          <div className="card-value">{runRates?.summary?.health_score || 100}</div>
          <div className="card-sub">out of 100</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="sla-tabs">
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={activeTab === 'measures' ? 'active' : ''}
          onClick={() => setActiveTab('measures')}
        >
          SLA Measures
        </button>
        <button
          className={activeTab === 'alerts' ? 'active' : ''}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alerts.length})
        </button>
        <button
          className={activeTab === 'bottlenecks' ? 'active' : ''}
          onClick={() => setActiveTab('bottlenecks')}
        >
          Bottlenecks
        </button>
        <button
          className={activeTab === 'reports' ? 'active' : ''}
          onClick={() => setActiveTab('reports')}
        >
          Reports
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <>
          <div className="sla-section">
            <h2><span className="icon">📊</span> Performance Overview</h2>
            <div className="trend-stats">
              <div className="trend-stat">
                <div className={`value ${(summary?.overall_on_time_rate || 0) >= 85 ? 'positive' : 'negative'}`}>
                  {(summary?.overall_on_time_rate || 0).toFixed(1)}%
                </div>
                <div className="label">On-Time Rate (30 days)</div>
              </div>
              <div className="trend-stat">
                <div className="value">
                  {(summary?.avg_completion_time_hours || 0).toFixed(1)}h
                </div>
                <div className="label">Avg Completion Time</div>
              </div>
              <div className="trend-stat">
                <div className="value">{summary?.total_active_milestones || 0}</div>
                <div className="label">Active Milestones</div>
              </div>
              <div className="trend-stat">
                <div className="value">{measures.length}</div>
                <div className="label">SLA Measures</div>
              </div>
            </div>

            {/* Milestone Breakdown */}
            {summary?.milestone_breakdown && Object.keys(summary.milestone_breakdown).length > 0 && (
              <div style={{ marginTop: '24px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>
                  Active Milestones by Stage
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                  {Object.entries(summary.milestone_breakdown).map(([type, stats]) => (
                    <div key={type} style={{
                      padding: '12px',
                      background: '#f9fafb',
                      borderRadius: '8px',
                      fontSize: '13px'
                    }}>
                      <div style={{ fontWeight: '500', marginBottom: '4px' }}>
                        {formatMilestoneType(type)}
                      </div>
                      <div style={{ color: '#6b7280' }}>
                        {stats.total} total
                        {stats.at_risk > 0 && <span style={{ color: '#f59e0b' }}> ({stats.at_risk} at risk)</span>}
                        {stats.overdue > 0 && <span style={{ color: '#ef4444' }}> ({stats.overdue} overdue)</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Recent Alerts Preview */}
          {alerts.length > 0 && (
            <div className="sla-section">
              <h2><span className="icon">🔔</span> Recent Alerts</h2>
              <div className="alerts-list">
                {alerts.slice(0, 3).map((alert) => (
                  <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                    <span className="alert-icon">
                      {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                    </span>
                    <div className="alert-content">
                      <div className="alert-title">{alert.title}</div>
                      <div className="alert-message">{alert.message}</div>
                      <div className="alert-meta">
                        <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                        <span>Triggered: {new Date(alert.triggered_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="alert-actions">
                      <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                        Acknowledge
                      </button>
                      <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {alerts.length > 3 && (
                <button
                  onClick={() => setActiveTab('alerts')}
                  style={{
                    marginTop: '12px',
                    padding: '8px 16px',
                    background: 'none',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    cursor: 'pointer'
                  }}
                >
                  View All Alerts ({alerts.length})
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* SLA Measures Tab */}
      {activeTab === 'measures' && (
        <div className="sla-section">
          <h2>
            <span className="icon">⏱️</span> SLA Measures Configuration
            <button
              onClick={() => {
                setEditingMeasure(null);
                setShowEditModal(true);
              }}
              style={{
                marginLeft: 'auto',
                padding: '8px 16px',
                background: '#218D8D',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              + Add Measure
            </button>
          </h2>

          {measures.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <h3>No SLA Measures Configured</h3>
              <p>Set up SLA measures to start tracking loan lifecycle milestones</p>
              <button onClick={runMigration}>Initialize Default Measures</button>
            </div>
          ) : (
            <table className="measures-table">
              <thead>
                <tr>
                  <th>Milestone</th>
                  <th>Target</th>
                  <th>Trigger From</th>
                  <th>Warning At</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {/* Lead Stage Section */}
                {groupedMeasures.lead.length > 0 && (
                  <tr className="stage-header-row">
                    <td colSpan="6" style={{
                      background: '#e0f2f1',
                      padding: '10px 16px',
                      fontWeight: '600',
                      fontSize: '13px',
                      color: '#00695c',
                      borderBottom: '2px solid #26a69a'
                    }}>
                      📋 Lead Stage Milestones ({groupedMeasures.lead.length})
                    </td>
                  </tr>
                )}
                {groupedMeasures.lead.map((measure) => renderMeasureRow(measure))}

                {/* Loan Stage Section */}
                {groupedMeasures.loan.length > 0 && (
                  <tr className="stage-header-row">
                    <td colSpan="6" style={{
                      background: '#e3f2fd',
                      padding: '10px 16px',
                      fontWeight: '600',
                      fontSize: '13px',
                      color: '#1565c0',
                      borderBottom: '2px solid #42a5f5'
                    }}>
                      🏦 Active Loan Stage Milestones ({groupedMeasures.loan.length})
                    </td>
                  </tr>
                )}
                {groupedMeasures.loan.map((measure) => renderMeasureRow(measure))}

                {/* Other Milestones Section */}
                {groupedMeasures.other.length > 0 && (
                  <tr className="stage-header-row">
                    <td colSpan="6" style={{
                      background: '#f3f4f6',
                      padding: '10px 16px',
                      fontWeight: '600',
                      fontSize: '13px',
                      color: '#6b7280',
                      borderBottom: '2px solid #9ca3af'
                    }}>
                      📁 Other Milestones ({groupedMeasures.other.length})
                    </td>
                  </tr>
                )}
                {groupedMeasures.other.map((measure) => renderMeasureRow(measure))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="sla-section">
          <h2><span className="icon">🔔</span> All Active Alerts</h2>
          {alerts.length === 0 ? (
            <div className="empty-state">
              <div className="icon">✅</div>
              <h3>No Active Alerts</h3>
              <p>All milestones are on track</p>
            </div>
          ) : (
            <div className="alerts-list">
              {alerts.map((alert) => (
                <div key={alert.id} className={`alert-item ${alert.alert_type}`}>
                  <span className="alert-icon">
                    {alert.alert_type === 'overdue' ? '🚨' : alert.alert_type === 'at_risk' ? '⚠️' : 'ℹ️'}
                  </span>
                  <div className="alert-content">
                    <div className="alert-title">{alert.title}</div>
                    <div className="alert-message">{alert.message}</div>
                    <div className="alert-meta">
                      <span>Loan: {alert.loan_number || alert.loan_id || 'N/A'}</span>
                      <span>Triggered: {new Date(alert.triggered_at).toLocaleString()}</span>
                      <span>Status: {alert.status}</span>
                    </div>
                  </div>
                  <div className="alert-actions">
                    <button className="btn-acknowledge" onClick={() => acknowledgeAlert(alert.id)}>
                      Acknowledge
                    </button>
                    <button className="btn-resolve" onClick={() => resolveAlert(alert.id)}>
                      Resolve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Bottlenecks Tab */}
      {activeTab === 'bottlenecks' && (
        <div className="sla-section">
          <h2><span className="icon">🚧</span> Bottleneck Analysis</h2>
          <p style={{ color: '#6b7280', marginBottom: '20px' }}>
            Stages causing the most delays based on the last 30 days of data
          </p>
          {bottlenecks.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📈</div>
              <h3>No Bottlenecks Detected</h3>
              <p>All stages are performing within acceptable parameters</p>
            </div>
          ) : (
            <div className="bottleneck-list">
              {bottlenecks.map((bottleneck, index) => (
                <div key={bottleneck.milestone_type} className="bottleneck-item">
                  <div className={`bottleneck-rank ${index === 1 ? 'rank-2' : index === 2 ? 'rank-3' : ''}`}>
                    {index + 1}
                  </div>
                  <div className="bottleneck-content">
                    <div className="bottleneck-name">{formatMilestoneType(bottleneck.milestone_type)}</div>
                    <div className="bottleneck-stats">
                      <span>Avg delay: {bottleneck.avg_delay_hours?.toFixed(1) || 0} hours</span>
                      <span>Frequency: {bottleneck.delay_frequency_pct?.toFixed(0) || 0}% of loans</span>
                      <span>Affected: {bottleneck.total_affected_loans || 0} loans</span>
                    </div>
                  </div>
                  <div className="bottleneck-bar">
                    <div
                      className="fill"
                      style={{ width: `${Math.min(bottleneck.delay_frequency_pct || 0, 100)}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && (
        <ReportsTab
          runRates={runRates}
          teamMembers={teamMembers}
          reportHistory={reportHistory}
          sendingReport={sendingReport}
          onSendReport={sendReport}
          formatMilestoneType={formatMilestoneType}
        />
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <EditMeasureModal
          measure={editingMeasure}
          onSave={saveMeasure}
          onClose={() => {
            setShowEditModal(false);
            setEditingMeasure(null);
          }}
        />
      )}
    </div>
  );
};

// Reports Tab Component
const ReportsTab = ({ runRates, teamMembers, reportHistory, sendingReport, onSendReport, formatMilestoneType }) => {
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  const [customEmail, setCustomEmail] = useState('');
  const [reportOptions, setReportOptions] = useState({
    includeRunRates: true,
    includeForecasts: true,
    includeBottlenecks: true
  });
  const [sendStatus, setSendStatus] = useState(null);

  const handleAddCustomEmail = () => {
    if (customEmail && customEmail.includes('@')) {
      setSelectedRecipients(prev => [...prev, { email: customEmail, name: customEmail }]);
      setCustomEmail('');
    }
  };

  const handleToggleRecipient = (email) => {
    setSelectedRecipients(prev => {
      const exists = prev.find(r => r.email === email);
      if (exists) {
        return prev.filter(r => r.email !== email);
      } else {
        const member = teamMembers.find(m => m.email === email);
        return [...prev, { email, name: member?.full_name || member?.name || email }];
      }
    });
  };

  const handleSendReports = async () => {
    if (selectedRecipients.length === 0) {
      setSendStatus({ type: 'error', message: 'Please select at least one recipient' });
      return;
    }

    setSendStatus({ type: 'sending', message: 'Sending reports...' });
    const results = [];

    for (const recipient of selectedRecipients) {
      const result = await onSendReport(recipient.email, reportOptions);
      results.push({ email: recipient.email, ...result });
    }

    const successCount = results.filter(r => r.success).length;
    const failCount = results.filter(r => !r.success).length;

    if (failCount === 0) {
      setSendStatus({ type: 'success', message: `Successfully sent ${successCount} report(s)` });
    } else {
      setSendStatus({ type: 'warning', message: `Sent ${successCount}, failed ${failCount}` });
    }

    // Clear selection after sending
    setTimeout(() => {
      setSelectedRecipients([]);
      setSendStatus(null);
    }, 3000);
  };

  return (
    <>
      {/* Run Rate Summary */}
      <div className="sla-section">
        <h2><span className="icon">📈</span> Run Rate Summary</h2>
        <p style={{ color: '#6b7280', marginBottom: '20px' }}>
          Current performance metrics and inventory forecasting
        </p>

        {runRates ? (
          <>
            <div className="trend-stats" style={{ marginBottom: '24px' }}>
              <div className="trend-stat">
                <div className="value" style={{ color: runRates.summary?.health_score >= 80 ? '#10b981' : runRates.summary?.health_score >= 60 ? '#f59e0b' : '#ef4444' }}>
                  {runRates.summary?.health_score || 100}
                </div>
                <div className="label">Health Score</div>
              </div>
              <div className="trend-stat">
                <div className="value">{runRates.summary?.total_active_milestones || 0}</div>
                <div className="label">Active Milestones</div>
              </div>
              <div className="trend-stat">
                <div className="value" style={{ color: '#f59e0b' }}>{runRates.summary?.total_at_risk || 0}</div>
                <div className="label">At Risk</div>
              </div>
              <div className="trend-stat">
                <div className="value" style={{ color: '#ef4444' }}>{runRates.summary?.total_overdue || 0}</div>
                <div className="label">Overdue</div>
              </div>
            </div>

            {/* Run Rates Table */}
            {runRates.milestone_run_rates && runRates.milestone_run_rates.length > 0 && (
              <table className="measures-table">
                <thead>
                  <tr>
                    <th>Milestone</th>
                    <th>Daily Rate</th>
                    <th>Weekly Rate</th>
                    <th>On-Time %</th>
                    <th>Trend</th>
                    <th>Inventory</th>
                  </tr>
                </thead>
                <tbody>
                  {runRates.milestone_run_rates.map((rr) => {
                    const forecast = runRates.inventory_forecasts?.find(f => f.milestone_type === rr.milestone_type);
                    return (
                      <tr key={rr.milestone_type}>
                        <td>
                          <div className="milestone-name">{formatMilestoneType(rr.milestone_type)}</div>
                        </td>
                        <td>{rr.daily_run_rate}</td>
                        <td>{rr.weekly_run_rate}</td>
                        <td>
                          <span style={{
                            color: rr.on_time_rate >= 85 ? '#10b981' : rr.on_time_rate >= 70 ? '#f59e0b' : '#ef4444'
                          }}>
                            {rr.on_time_rate}%
                          </span>
                        </td>
                        <td>
                          <span className={`trend-badge trend-${rr.trend}`}>
                            {rr.trend === 'improving' ? '↑' : rr.trend === 'declining' ? '↓' : '→'} {rr.trend}
                          </span>
                        </td>
                        <td>
                          {forecast?.current_inventory || 0}
                          {forecast?.is_potential_bottleneck && (
                            <span className="bottleneck-warning" title="Potential bottleneck">⚠️</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <div className="empty-state">
            <div className="icon">📊</div>
            <h3>No Run Rate Data Available</h3>
            <p>Run rate data will appear once milestones are being tracked</p>
          </div>
        )}
      </div>

      {/* Send Reports Section */}
      <div className="sla-section">
        <h2><span className="icon">📧</span> Send Reports</h2>
        <p style={{ color: '#6b7280', marginBottom: '20px' }}>
          Send SLA run rate reports to team members and stakeholders
        </p>

        <div className="report-builder">
          {/* Recipients Selection */}
          <div className="report-recipients">
            <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>Select Recipients</h3>

            {/* Team Members */}
            {teamMembers.length > 0 && (
              <div className="team-members-list" style={{ marginBottom: '16px' }}>
                {teamMembers.map((member) => (
                  <label
                    key={member.email || member.id}
                    className="recipient-checkbox"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 12px',
                      background: selectedRecipients.find(r => r.email === member.email) ? '#e0f2f1' : '#f9fafb',
                      borderRadius: '6px',
                      marginBottom: '8px',
                      cursor: 'pointer',
                      border: selectedRecipients.find(r => r.email === member.email) ? '1px solid #218D8D' : '1px solid transparent'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={!!selectedRecipients.find(r => r.email === member.email)}
                      onChange={() => handleToggleRecipient(member.email)}
                      style={{ marginRight: '10px' }}
                    />
                    <div>
                      <div style={{ fontWeight: '500' }}>{member.full_name || member.name || 'User'}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>{member.email}</div>
                    </div>
                    {member.role && (
                      <span style={{
                        marginLeft: 'auto',
                        fontSize: '11px',
                        padding: '2px 8px',
                        background: '#e5e7eb',
                        borderRadius: '10px',
                        color: '#6b7280'
                      }}>
                        {member.role}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}

            {/* Custom Email Input */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <input
                type="email"
                value={customEmail}
                onChange={(e) => setCustomEmail(e.target.value)}
                placeholder="Add custom email address..."
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px'
                }}
                onKeyPress={(e) => e.key === 'Enter' && handleAddCustomEmail()}
              />
              <button
                onClick={handleAddCustomEmail}
                style={{
                  padding: '10px 16px',
                  background: '#f3f4f6',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  cursor: 'pointer'
                }}
              >
                Add
              </button>
            </div>

            {/* Selected Recipients */}
            {selectedRecipients.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                  Selected: {selectedRecipients.length} recipient(s)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {selectedRecipients.map((r) => (
                    <span
                      key={r.email}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '4px 10px',
                        background: '#218D8D',
                        color: 'white',
                        borderRadius: '16px',
                        fontSize: '12px'
                      }}
                    >
                      {r.name || r.email}
                      <button
                        onClick={() => setSelectedRecipients(prev => prev.filter(x => x.email !== r.email))}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'white',
                          cursor: 'pointer',
                          padding: 0,
                          fontSize: '14px',
                          lineHeight: 1
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Report Options */}
          <div className="report-options" style={{ marginBottom: '20px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px' }}>Report Contents</h3>
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeRunRates}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeRunRates: e.target.checked }))}
                />
                Run Rates & Trends
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeForecasts}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeForecasts: e.target.checked }))}
                />
                Inventory Forecasts
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={reportOptions.includeBottlenecks}
                  onChange={(e) => setReportOptions(prev => ({ ...prev, includeBottlenecks: e.target.checked }))}
                />
                Bottleneck Analysis
              </label>
            </div>
          </div>

          {/* Send Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              onClick={handleSendReports}
              disabled={sendingReport || selectedRecipients.length === 0}
              style={{
                padding: '12px 24px',
                background: selectedRecipients.length === 0 ? '#9ca3af' : '#218D8D',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: selectedRecipients.length === 0 ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: '500',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {sendingReport ? (
                <>
                  <span className="loading-spinner" style={{ width: '16px', height: '16px', marginRight: '4px' }}></span>
                  Sending...
                </>
              ) : (
                <>
                  📧 Send Report{selectedRecipients.length > 1 ? 's' : ''}
                </>
              )}
            </button>

            {sendStatus && (
              <span style={{
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                background: sendStatus.type === 'success' ? '#d1fae5' : sendStatus.type === 'error' ? '#fee2e2' : sendStatus.type === 'warning' ? '#fef3c7' : '#e0f2fe',
                color: sendStatus.type === 'success' ? '#065f46' : sendStatus.type === 'error' ? '#991b1b' : sendStatus.type === 'warning' ? '#92400e' : '#0369a1'
              }}>
                {sendStatus.message}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Report History */}
      {reportHistory.length > 0 && (
        <div className="sla-section">
          <h2><span className="icon">📋</span> Recent Reports Sent</h2>
          <table className="measures-table">
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Sent At</th>
                <th>Health Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {reportHistory.map((report) => (
                <tr key={report.id}>
                  <td>{report.email}</td>
                  <td>{new Date(report.sentAt).toLocaleString()}</td>
                  <td>{report.summary?.health_score || '-'}</td>
                  <td>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '10px',
                      fontSize: '12px',
                      background: report.status === 'sent' ? '#d1fae5' : '#fee2e2',
                      color: report.status === 'sent' ? '#065f46' : '#991b1b'
                    }}>
                      {report.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
};

// Edit Measure Modal Component
const EditMeasureModal = ({ measure, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    name: measure?.name || '',
    milestone_type: measure?.milestone_type || 'lead_response',
    description: measure?.description || '',
    target_value: measure?.target_value || 4,
    target_unit: measure?.target_unit || 'hours',
    trigger_from: measure?.trigger_from || 'previous_milestone',
    trigger_from_is_default: measure?.trigger_from_is_default ?? false,
    warning_threshold_pct: measure?.warning_threshold_pct || 75,
    critical_threshold_pct: measure?.critical_threshold_pct || 100,
    business_hours_only: measure?.business_hours_only ?? true,
    is_active: measure?.is_active ?? true
  });

  const milestoneTypes = [
    'lead_response', 'initial_consultation', 'pre_qualified', 'preapproval',
    'application_submitted', 'documents_requested', 'documents_received',
    'document_collection', 'application_complete',
    'submitted_to_processing', 'processing_start',
    'appraisal_ordered', 'appraisal_received',
    'title_ordered', 'title_received',
    'insurance_ordered', 'insurance_received',
    'submitted_to_uw', 'uw_decision', 'approved',
    'conditions_issued', 'conditions_cleared', 'clear_to_close',
    'closing_docs_out', 'closing_scheduled', 'closed', 'funded'
  ];

  // Trigger From options - what event starts the SLA timer
  const triggerFromOptions = [
    { value: 'lead_created', label: 'Lead Created' },
    { value: 'loan_created', label: 'Loan Created' },
    { value: 'previous_milestone', label: 'Previous Milestone Completed' },
    { value: 'lead_response', label: 'Lead Response' },
    { value: 'initial_consultation', label: 'Initial Consultation' },
    { value: 'pre_qualified', label: 'Pre-Qualified' },
    { value: 'preapproval', label: 'Pre-Approval' },
    { value: 'application_submitted', label: 'Application Submitted' },
    { value: 'documents_requested', label: 'Documents Requested' },
    { value: 'documents_received', label: 'Documents Received' },
    { value: 'document_collection', label: 'Document Collection' },
    { value: 'application_complete', label: 'Application Complete' },
    { value: 'submitted_to_processing', label: 'Submitted to Processing' },
    { value: 'processing_start', label: 'Processing Start' },
    { value: 'appraisal_ordered', label: 'Appraisal Ordered' },
    { value: 'appraisal_received', label: 'Appraisal Received' },
    { value: 'title_ordered', label: 'Title Ordered' },
    { value: 'title_received', label: 'Title Received' },
    { value: 'insurance_ordered', label: 'Insurance Ordered' },
    { value: 'insurance_received', label: 'Insurance Received' },
    { value: 'submitted_to_uw', label: 'Submitted to Underwriting' },
    { value: 'uw_decision', label: 'Underwriting Decision' },
    { value: 'approved', label: 'Approved' },
    { value: 'conditions_issued', label: 'Conditions Issued' },
    { value: 'conditions_cleared', label: 'Conditions Cleared' },
    { value: 'clear_to_close', label: 'Clear to Close' },
    { value: 'closing_docs_out', label: 'Closing Docs Out' },
    { value: 'closing_scheduled', label: 'Closing Scheduled' },
    { value: 'closed', label: 'Closed' }
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{measure ? 'Edit SLA Measure' : 'Add SLA Measure'}</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Milestone Type</label>
              <select
                value={formData.milestone_type}
                onChange={e => setFormData({ ...formData, milestone_type: e.target.value })}
                disabled={!!measure}
              >
                {milestoneTypes.map(type => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Target Value</label>
                <input
                  type="number"
                  value={formData.target_value}
                  onChange={e => setFormData({ ...formData, target_value: parseFloat(e.target.value) })}
                  step="0.5"
                  required
                />
                <p style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                  Use negative values for "before" events (e.g., -10 = 10 days before trigger event)
                </p>
              </div>
              <div className="form-group">
                <label>Target Unit</label>
                <select
                  value={formData.target_unit}
                  onChange={e => setFormData({ ...formData, target_unit: e.target.value })}
                >
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                  <option value="business_days">Business Days</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label>Trigger From (SLA Timer Starts When)</label>
              <select
                value={formData.trigger_from}
                onChange={e => setFormData({ ...formData, trigger_from: e.target.value })}
                style={{ width: '100%' }}
              >
                {triggerFromOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                The SLA timer will start counting from this event
              </p>
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={formData.trigger_from_is_default}
                  onChange={e => setFormData({ ...formData, trigger_from_is_default: e.target.checked })}
                />
                Set as Default Trigger for this Milestone
              </label>
              <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                If checked, this trigger will be the default for all "{formData.milestone_type.replace(/_/g, ' ')}" milestones
              </p>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Warning Threshold (%)</label>
                <input
                  type="number"
                  value={formData.warning_threshold_pct}
                  onChange={e => setFormData({ ...formData, warning_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  required
                />
              </div>
              <div className="form-group">
                <label>Critical Threshold (%)</label>
                <input
                  type="number"
                  value={formData.critical_threshold_pct}
                  onChange={e => setFormData({ ...formData, critical_threshold_pct: parseFloat(e.target.value) })}
                  min="0"
                  max="200"
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.business_hours_only}
                  onChange={e => setFormData({ ...formData, business_hours_only: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Business Hours Only
              </label>
            </div>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Active
              </label>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-save">Save Measure</button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default SLASettings;
