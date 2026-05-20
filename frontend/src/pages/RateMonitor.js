import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { rateMonitorAPI, rateSheetAPI } from '../services/api';
import RateTargetModal from '../components/RateTargetModal';
import './RateMonitor.css';
import { toast } from '../utils/toast';

function RateMonitor() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dashboard data
  const [metrics, setMetrics] = useState(null);

  // Targets data
  const [targets, setTargets] = useState([]);
  const [targetsTotal, setTargetsTotal] = useState(0);
  const [targetFilters, setTargetFilters] = useState({
    status: '',
    isActive: true,
  });

  // Alerts data
  const [alerts, setAlerts] = useState([]);
  const [alertsTotal, setAlertsTotal] = useState(0);
  const [alertFilters, setAlertFilters] = useState({
    status: 'pending',
    priority: '',
  });

  // Modal state
  const [showTargetModal, setShowTargetModal] = useState(false);
  const [editingTarget, setEditingTarget] = useState(null);

  // Current rates
  const [currentRates, setCurrentRates] = useState(null);

  // Rate Sheet Upload state
  const [rateSheets, setRateSheets] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [selectedSheet, setSelectedSheet] = useState(null);
  const [sheetRates, setSheetRates] = useState([]);
  const fileInputRef = useRef(null);

  // Opportunities state
  const [opportunities, setOpportunities] = useState([]);
  const [opportunitiesTotal, setOpportunitiesTotal] = useState(0);
  const [opportunitiesMetrics, setOpportunitiesMetrics] = useState(null);
  const [opportunityFilters, setOpportunityFilters] = useState({
    status: 'identified',
    priority: '',
  });
  const [selectedOpportunities, setSelectedOpportunities] = useState([]);
  const [processingOutreach, setProcessingOutreach] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await rateMonitorAPI.getDashboard();
      setMetrics(data.metrics || null);
      setCurrentRates(data.current_rates || null);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      // On 404 or network error, use empty defaults so the page still renders
      setMetrics(null);
      setCurrentRates(null);
    }
  }, []);

  const loadTargets = useCallback(async () => {
    try {
      const params = {};
      if (targetFilters.status) params.status = targetFilters.status;
      if (targetFilters.isActive !== null) params.is_active = targetFilters.isActive;

      const data = await rateMonitorAPI.getTargets(params);
      setTargets(data?.targets || []);
      setTargetsTotal(data?.total || 0);
    } catch (err) {
      console.error('Failed to load targets:', err);
      setTargets([]);
      setTargetsTotal(0);
    }
  }, [targetFilters]);

  const loadAlerts = useCallback(async () => {
    try {
      const params = {};
      if (alertFilters.status) params.status = alertFilters.status;
      if (alertFilters.priority) params.priority = alertFilters.priority;

      const data = await rateMonitorAPI.getAlerts(params);
      setAlerts(data?.alerts || []);
      setAlertsTotal(data?.total || 0);
    } catch (err) {
      console.error('Failed to load alerts:', err);
      setAlerts([]);
      setAlertsTotal(0);
    }
  }, [alertFilters]);

  const loadRateSheets = useCallback(async () => {
    try {
      const data = await rateSheetAPI.getSheets({ limit: 20 });
      setRateSheets(data?.sheets || []);
    } catch (err) {
      console.error('Failed to load rate sheets:', err);
      setRateSheets([]);
    }
  }, []);

  const loadOpportunities = useCallback(async () => {
    try {
      const params = {};
      if (opportunityFilters.status) params.status = opportunityFilters.status;
      if (opportunityFilters.priority) params.priority = opportunityFilters.priority;

      const [oppData, metricsData] = await Promise.allSettled([
        rateSheetAPI.getOpportunities(params),
        rateSheetAPI.getOpportunitiesDashboard(),
      ]);

      const oppResult = oppData.status === 'fulfilled' ? oppData.value : null;
      const metricsResult = metricsData.status === 'fulfilled' ? metricsData.value : null;

      setOpportunities(oppResult?.opportunities || []);
      setOpportunitiesTotal(oppResult?.total || 0);
      setOpportunitiesMetrics(metricsResult || null);
    } catch (err) {
      console.error('Failed to load opportunities:', err);
      setOpportunities([]);
      setOpportunitiesTotal(0);
      setOpportunitiesMetrics(null);
    }
  }, [opportunityFilters]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.allSettled([loadDashboard(), loadTargets(), loadAlerts(), loadRateSheets(), loadOpportunities()]);
      setLoading(false);
    };
    loadData();
  }, [loadDashboard, loadTargets, loadAlerts, loadRateSheets, loadOpportunities]);

  // Rate Sheet handlers
  const handleFileSelect = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const allowedTypes = ['.pdf', '.xlsx', '.xls', '.csv'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedTypes.includes(ext)) {
      toast.error('Please upload a PDF, Excel, or CSV file');
      return;
    }

    setUploading(true);
    setUploadProgress('Uploading...');

    try {
      const result = await rateSheetAPI.uploadSheet(file);
      if (result.success) {
        setUploadProgress('Processing...');
        await loadRateSheets();
        setUploadProgress(null);
        toast.success(`Rate sheet uploaded! ${result.rate_sheet_id ? 'Parsing in progress.' : ''}`);
      } else {
        toast.error(result.error || 'Upload failed');
        setUploadProgress(null);
      }
    } catch (err) {
      console.error('Upload failed:', err);
      toast.error('Failed to upload rate sheet');
      setUploadProgress(null);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleViewSheetRates = async (sheet) => {
    setSelectedSheet(sheet);
    try {
      const data = await rateSheetAPI.getSheetRates(sheet.id);
      setSheetRates(data?.rates || []);
    } catch (err) {
      console.error('Failed to load rates:', err);
      setSheetRates([]);
    }
  };

  const handleScanSheet = async (sheetId) => {
    if (!window.confirm('Scan for refinance opportunities using this rate sheet?')) return;

    try {
      const result = await rateSheetAPI.scanForOpportunities(sheetId);
      if (result.success) {
        toast.success(`Scan complete! Found ${result.opportunities_created} opportunities from ${result.loans_scanned} loans.`);
        await loadOpportunities();
      } else {
        toast.error(result.error || 'Scan failed');
      }
    } catch (err) {
      console.error('Scan failed:', err);
      toast.error('Failed to scan for opportunities');
    }
  };

  const handleDeleteSheet = async (sheetId) => {
    if (!window.confirm('Delete this rate sheet?')) return;

    try {
      await rateSheetAPI.deleteSheet(sheetId);
      await loadRateSheets();
      if (selectedSheet?.id === sheetId) {
        setSelectedSheet(null);
        setSheetRates([]);
      }
    } catch (err) {
      console.error('Delete failed:', err);
      toast.error('Failed to delete rate sheet');
    }
  };

  // Opportunity handlers
  const handleSelectOpportunity = (oppId, checked) => {
    if (checked) {
      setSelectedOpportunities([...selectedOpportunities, oppId]);
    } else {
      setSelectedOpportunities(selectedOpportunities.filter(id => id !== oppId));
    }
  };

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedOpportunities(opportunities.map(o => o.id));
    } else {
      setSelectedOpportunities([]);
    }
  };

  const handleSingleOutreach = async (oppId, skipSms = false) => {
    const action = skipSms ? 'call' : 'outreach (SMS + Call)';
    if (!window.confirm(`Start ${action} for this opportunity?`)) return;

    setProcessingOutreach(true);
    try {
      let result;
      if (skipSms) {
        result = await rateSheetAPI.initiateCall(oppId);
      } else {
        result = await rateSheetAPI.triggerOutreach(oppId);
      }

      if (result.success) {
        toast.success('Outreach initiated!');
        await loadOpportunities();
      } else {
        toast.error(result.error || 'Outreach failed');
      }
    } catch (err) {
      console.error('Outreach failed:', err);
      toast.error('Failed to initiate outreach');
    } finally {
      setProcessingOutreach(false);
    }
  };

  const handleBulkOutreach = async () => {
    if (selectedOpportunities.length === 0) {
      toast.error('Please select opportunities first');
      return;
    }

    if (!window.confirm(`Start outreach for ${selectedOpportunities.length} opportunities?`)) return;

    setProcessingOutreach(true);
    try {
      const result = await rateSheetAPI.bulkOutreach(selectedOpportunities, false);
      toast.success(`Outreach complete: ${result.success_count} succeeded, ${result.error_count} failed`);
      setSelectedOpportunities([]);
      await loadOpportunities();
    } catch (err) {
      console.error('Bulk outreach failed:', err);
      toast.error('Bulk outreach failed');
    } finally {
      setProcessingOutreach(false);
    }
  };

  const handleUpdateOpportunityStatus = async (oppId, status) => {
    try {
      await rateSheetAPI.updateOpportunity(oppId, { status });
      await loadOpportunities();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const handleMarkConverted = async (oppId) => {
    if (!window.confirm('Mark this opportunity as converted?')) return;

    try {
      await rateSheetAPI.markConverted(oppId);
      await loadOpportunities();
    } catch (err) {
      console.error('Failed to mark converted:', err);
    }
  };

  // Existing handlers
  const handleCreateTarget = () => {
    setEditingTarget(null);
    setShowTargetModal(true);
  };

  const handleEditTarget = (target) => {
    setEditingTarget(target);
    setShowTargetModal(true);
  };

  const handleSaveTarget = async (targetData) => {
    try {
      if (editingTarget) {
        await rateMonitorAPI.updateTarget(editingTarget.id, targetData);
      } else {
        await rateMonitorAPI.createTarget(targetData);
      }
      setShowTargetModal(false);
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to save target:', err);
      toast.error('Failed to save target: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteTarget = async (targetId) => {
    if (!window.confirm('Are you sure you want to delete this target?')) return;

    try {
      await rateMonitorAPI.deleteTarget(targetId);
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to delete target:', err);
      toast.error('Failed to delete target');
    }
  };

  const handleToggleActive = async (target) => {
    try {
      await rateMonitorAPI.updateTarget(target.id, { is_active: !target.is_active });
      loadTargets();
      loadDashboard();
    } catch (err) {
      console.error('Failed to toggle target:', err);
    }
  };

  const handleInitiateCall = async (alertId) => {
    if (!window.confirm('Initiate an AI call to this client about refinancing?')) return;

    try {
      const result = await rateMonitorAPI.initiateCall(alertId);
      if (result.status === 'initiated') {
        toast.success('Call initiated successfully!');
        loadAlerts();
      } else {
        toast.success(result.message || 'Call could not be initiated');
      }
    } catch (err) {
      console.error('Failed to initiate call:', err);
      toast.error('Failed to initiate call');
    }
  };

  const handleUpdateAlertStatus = async (alertId, status) => {
    try {
      await rateMonitorAPI.updateAlert(alertId, { status });
      loadAlerts();
      loadDashboard();
    } catch (err) {
      console.error('Failed to update alert:', err);
    }
  };

  const handleViewMumClient = (mumClientId) => {
    navigate(`/portfolio/mum/${mumClientId}`);
  };

  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatRate = (rate) => {
    if (!rate && rate !== 0) return '-';
    return `${parseFloat(rate).toFixed(3)}%`;
  };

  const getPriorityClass = (priority) => {
    switch (priority) {
      case 'urgent': return 'rm-priority-urgent';
      case 'high': return 'rm-priority-high';
      case 'medium': return 'rm-priority-medium';
      case 'low': return 'rm-priority-low';
      default: return '';
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'pending': return 'rm-status-pending';
      case 'identified': return 'rm-status-pending';
      case 'acknowledged': return 'rm-status-acknowledged';
      case 'sms_sent': return 'rm-status-acknowledged';
      case 'called': return 'rm-status-called';
      case 'scheduled': return 'rm-status-called';
      case 'converted': return 'rm-status-converted';
      case 'dismissed': return 'rm-status-dismissed';
      case 'declined': return 'rm-status-dismissed';
      default: return '';
    }
  };

  const getSheetStatusClass = (status) => {
    switch (status) {
      case 'parsed': return 'rm-status-success';
      case 'processing': return 'rm-status-processing';
      case 'failed': return 'rm-status-error';
      default: return 'rm-status-pending';
    }
  };

  if (loading) {
    return (
      <div className="rm-page">
        <div className="rm-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="rm-page">
      <div className="rm-header">
        <div className="rm-header-content">
          <h1 className="rm-title">Rate Monitor</h1>
          <p className="rm-subtitle">Track refinance opportunities for MUM clients</p>
        </div>
        <div className="rm-header-actions">
          <button className="rm-btn-primary" onClick={handleCreateTarget}>
            + New Rate Target
          </button>
        </div>
      </div>

      {/* Current Rates Banner */}
      {currentRates && (
        <div className="rm-rates-banner">
          <div className="rm-rates-banner-content">
            <span className="rm-rates-label">Current Rates:</span>
            <span className="rm-rate-item">
              <strong>30-Year:</strong> {formatRate(currentRates['30_year'])}
            </span>
            <span className="rm-rate-item">
              <strong>15-Year:</strong> {formatRate(currentRates['15_year'])}
            </span>
            {currentRates.is_mock && (
              <span className="rm-mock-badge">Mock Data</span>
            )}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="rm-tabs">
        <button
          className={`rm-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`rm-tab ${activeTab === 'rateSheets' ? 'active' : ''}`}
          onClick={() => setActiveTab('rateSheets')}
        >
          Rate Sheets ({rateSheets.length})
        </button>
        <button
          className={`rm-tab ${activeTab === 'opportunities' ? 'active' : ''}`}
          onClick={() => setActiveTab('opportunities')}
        >
          Opportunities ({opportunitiesTotal})
        </button>
        <button
          className={`rm-tab ${activeTab === 'targets' ? 'active' : ''}`}
          onClick={() => setActiveTab('targets')}
        >
          Rate Targets ({targetsTotal})
        </button>
        <button
          className={`rm-tab ${activeTab === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveTab('alerts')}
        >
          Alerts ({alertsTotal})
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <div className="rm-dashboard">
          {metrics ? (
            <>
              <div className="rm-metrics-grid">
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.active_monitors ?? 0}</div>
                  <div className="rm-metric-label">Active Monitors</div>
                </div>
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.auto_call_enabled ?? 0}</div>
                  <div className="rm-metric-label">Auto-Call Enabled</div>
                </div>
                <div className="rm-metric-card highlight">
                  <div className="rm-metric-value">{metrics.pending_alerts ?? 0}</div>
                  <div className="rm-metric-label">Pending Alerts</div>
                </div>
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.high_priority_alerts ?? 0}</div>
                  <div className="rm-metric-label">High Priority</div>
                </div>
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.alerts_today ?? 0}</div>
                  <div className="rm-metric-label">Alerts Today</div>
                </div>
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.calls_made_this_month ?? 0}</div>
                  <div className="rm-metric-label">Calls This Month</div>
                </div>
                <div className="rm-metric-card">
                  <div className="rm-metric-value">{metrics.appointments_this_month ?? 0}</div>
                  <div className="rm-metric-label">Appointments</div>
                </div>
                <div className="rm-metric-card success">
                  <div className="rm-metric-value">{metrics.conversions_this_month ?? 0}</div>
                  <div className="rm-metric-label">Conversions</div>
                </div>
              </div>

              {/* Opportunities Summary */}
              {opportunitiesMetrics && (
                <div className="rm-opp-summary">
                  <h3>Refinance Opportunities</h3>
                  <div className="rm-summary-stats">
                    <div className="rm-stat">
                      <span className="rm-stat-value">{opportunitiesMetrics.pending_total || 0}</span>
                      <span className="rm-stat-label">Pending</span>
                    </div>
                    <div className="rm-stat">
                      <span className="rm-stat-value">{opportunitiesMetrics.by_priority?.urgent || 0}</span>
                      <span className="rm-stat-label">Urgent</span>
                    </div>
                    <div className="rm-stat highlight">
                      <span className="rm-stat-value">{formatCurrency(opportunitiesMetrics.total_monthly_savings)}</span>
                      <span className="rm-stat-label">Monthly Savings Potential</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="rm-savings-summary">
                <h3>Potential Monthly Savings from Pending Alerts</h3>
                <div className="rm-savings-value">{formatCurrency(metrics.pending_monthly_savings)}</div>
              </div>
            </>
          ) : (
            <div className="rm-empty-state">
              <p>No rate monitoring data available yet.</p>
              <p>Set up rate targets to start tracking refinance opportunities for your clients.</p>
              <button className="rm-btn-primary" onClick={handleCreateTarget} style={{ marginTop: '12px' }}>
                + New Rate Target
              </button>
            </div>
          )}

          {/* Recent Pending Alerts Preview */}
          <div className="rm-recent-alerts">
            <div className="rm-section-header">
              <h3>Recent Pending Alerts</h3>
              <button className="rm-btn-link" onClick={() => setActiveTab('alerts')}>
                View All
              </button>
            </div>
            <div className="rm-alerts-preview">
              {alerts.filter(a => a.status === 'pending').slice(0, 5).map(alert => (
                <div key={alert.id} className="rm-alert-preview-item">
                  <div className="rm-alert-info">
                    <span className="rm-client-name">{alert.client_name || 'Unknown Client'}</span>
                    <span className={`rm-priority-badge ${getPriorityClass(alert.priority)}`}>
                      {alert.priority}
                    </span>
                  </div>
                  <div className="rm-alert-savings">
                    {formatCurrency(alert.monthly_savings)}/month potential savings
                  </div>
                  <div className="rm-alert-actions">
                    <button
                      className="rm-btn-sm rm-btn-primary"
                      onClick={() => handleInitiateCall(alert.id)}
                    >
                      Call
                    </button>
                    <button
                      className="rm-btn-sm rm-btn-secondary"
                      onClick={() => handleViewMumClient(alert.mum_client_id)}
                    >
                      View
                    </button>
                  </div>
                </div>
              ))}
              {alerts.filter(a => a.status === 'pending').length === 0 && (
                <div className="rm-no-alerts">No pending alerts</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Rate Sheets Tab */}
      {activeTab === 'rateSheets' && (
        <div className="rm-sheets">
          {/* Upload Section */}
          <div className="rm-upload">
            <h3>Upload Rate Sheet</h3>
            <p className="rm-upload-desc">
              Upload a rate sheet (PDF/Excel) and AI will extract the rates. Then scan to find refinance opportunities.
            </p>
            <div className="rm-upload-controls">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept=".pdf,.xlsx,.xls,.csv"
                style={{ display: 'none' }}
              />
              <button
                className="rm-btn-primary"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                {uploading ? uploadProgress : 'Choose File'}
              </button>
              <span className="rm-file-types">Accepts: PDF, Excel, CSV</span>
            </div>
          </div>

          {/* Recent Uploads */}
          <div className="rm-recent-uploads">
            <h3>Recent Rate Sheets</h3>
            <div className="rm-sheets-list">
              {rateSheets.map(sheet => (
                <div key={sheet.id} className="rm-sheet-item">
                  <div className="rm-sheet-info">
                    <span className="rm-sheet-filename">{sheet.filename}</span>
                    <span className={`rm-sheet-status ${getSheetStatusClass(sheet.status)}`}>
                      {sheet.status}
                    </span>
                    {sheet.lender_name && (
                      <span className="rm-sheet-lender">{sheet.lender_name}</span>
                    )}
                  </div>
                  <div className="rm-sheet-meta">
                    <span>{sheet.rates_count || 0} rates</span>
                    <span>{new Date(sheet.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="rm-sheet-actions">
                    {sheet.status === 'parsed' && (
                      <>
                        <button
                          className="rm-btn-sm rm-btn-primary"
                          onClick={() => handleScanSheet(sheet.id)}
                        >
                          Scan Opportunities
                        </button>
                        <button
                          className="rm-btn-sm rm-btn-secondary"
                          onClick={() => handleViewSheetRates(sheet)}
                        >
                          View Rates
                        </button>
                      </>
                    )}
                    <button
                      className="rm-btn-sm rm-btn-danger"
                      onClick={() => handleDeleteSheet(sheet.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {rateSheets.length === 0 && (
                <div className="rm-no-sheets">No rate sheets uploaded yet</div>
              )}
            </div>
          </div>

          {/* Parsed Rates Modal/Section */}
          {selectedSheet && (
            <div className="rm-rates-section">
              <div className="rm-section-header">
                <h3>Rates from: {selectedSheet.filename}</h3>
                <button className="rm-btn-link" onClick={() => setSelectedSheet(null)}>
                  Close
                </button>
              </div>
              <div className="rm-rates-table-container">
                <table className="rm-table">
                  <thead>
                    <tr>
                      <th>Loan Type</th>
                      <th>Term</th>
                      <th>Rate</th>
                      <th>APR</th>
                      <th>Points</th>
                      <th>Credit Score</th>
                      <th>LTV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sheetRates.map(rate => (
                      <tr key={rate.id}>
                        <td>{rate.loan_type}</td>
                        <td>{rate.loan_term}yr</td>
                        <td className="rm-rate-cell">{formatRate(rate.rate)}</td>
                        <td>{rate.apr ? formatRate(rate.apr) : '-'}</td>
                        <td>{rate.points || 0}</td>
                        <td>
                          {rate.min_credit_score || '-'}
                          {rate.max_credit_score ? ` - ${rate.max_credit_score}` : ''}
                        </td>
                        <td>
                          {rate.max_ltv ? `<${rate.max_ltv}%` : '-'}
                        </td>
                      </tr>
                    ))}
                    {sheetRates.length === 0 && (
                      <tr>
                        <td colSpan="7" className="rm-no-data">No rates parsed</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Opportunities Tab */}
      {activeTab === 'opportunities' && (
        <div className="rm-opportunities">
          {/* Opportunities Metrics */}
          {opportunitiesMetrics && (
            <div className="rm-opp-metrics">
              <div className="rm-opp-metric">
                <span className="label">Identified:</span>
                <span className="value">{opportunitiesMetrics.by_status?.identified || 0}</span>
              </div>
              <div className="rm-opp-metric">
                <span className="label">SMS Sent:</span>
                <span className="value">{opportunitiesMetrics.by_status?.sms_sent || 0}</span>
              </div>
              <div className="rm-opp-metric">
                <span className="label">Called:</span>
                <span className="value">{opportunitiesMetrics.by_status?.called || 0}</span>
              </div>
              <div className="rm-opp-metric">
                <span className="label">Scheduled:</span>
                <span className="value">{opportunitiesMetrics.by_status?.scheduled || 0}</span>
              </div>
              <div className="rm-opp-metric success">
                <span className="label">Converted:</span>
                <span className="value">{opportunitiesMetrics.by_status?.converted || 0}</span>
              </div>
            </div>
          )}

          {/* Filters and Bulk Actions */}
          <div className="rm-filters">
            <select
              value={opportunityFilters.status}
              onChange={(e) => setOpportunityFilters({ ...opportunityFilters, status: e.target.value })}
            >
              <option value="">All Statuses</option>
              <option value="identified">Identified</option>
              <option value="sms_sent">SMS Sent</option>
              <option value="called">Called</option>
              <option value="scheduled">Scheduled</option>
              <option value="converted">Converted</option>
              <option value="declined">Declined</option>
            </select>
            <select
              value={opportunityFilters.priority}
              onChange={(e) => setOpportunityFilters({ ...opportunityFilters, priority: e.target.value })}
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            {selectedOpportunities.length > 0 && (
              <button
                className="rm-btn-primary"
                onClick={handleBulkOutreach}
                disabled={processingOutreach}
              >
                {processingOutreach ? 'Processing...' : `Start Outreach (${selectedOpportunities.length})`}
              </button>
            )}
          </div>

          {/* Opportunities Table */}
          <div className="rm-opp-table-container">
            <table className="rm-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      checked={selectedOpportunities.length === opportunities.length && opportunities.length > 0}
                      onChange={(e) => handleSelectAll(e.target.checked)}
                    />
                  </th>
                  <th>Client</th>
                  <th>Current Rate</th>
                  <th>New Rate</th>
                  <th>Monthly Savings</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {opportunities.map(opp => (
                  <tr key={opp.id} className={`rm-priority-row-${opp.priority}`}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedOpportunities.includes(opp.id)}
                        onChange={(e) => handleSelectOpportunity(opp.id, e.target.checked)}
                      />
                    </td>
                    <td>
                      <div className="rm-client-info">
                        <span className="rm-client-name">{opp.client_name || 'Unknown'}</span>
                        {opp.client_phone && (
                          <span className="rm-client-phone">{opp.client_phone}</span>
                        )}
                      </div>
                    </td>
                    <td className="rm-rate-cell">{formatRate(opp.current_rate)}</td>
                    <td className="rm-rate-cell highlight">{formatRate(opp.new_rate)}</td>
                    <td className="rm-savings-cell">{formatCurrency(opp.monthly_savings)}</td>
                    <td>
                      <span className={`rm-priority-badge ${getPriorityClass(opp.priority)}`}>
                        {opp.priority}
                      </span>
                    </td>
                    <td>
                      <span className={`rm-status-badge ${getStatusClass(opp.status)}`}>
                        {(opp.status || 'unknown').replace('_', ' ')}
                      </span>
                    </td>
                    <td className="rm-actions">
                      {(opp.status === 'identified' || opp.status === 'sms_sent') && (
                        <>
                          <button
                            className="rm-btn-sm rm-btn-primary"
                            onClick={() => handleSingleOutreach(opp.id, false)}
                            disabled={processingOutreach}
                            title="Send SMS + Call"
                          >
                            Outreach
                          </button>
                          <button
                            className="rm-btn-sm rm-btn-secondary"
                            onClick={() => handleSingleOutreach(opp.id, true)}
                            disabled={processingOutreach}
                            title="Call Only"
                          >
                            Call
                          </button>
                        </>
                      )}
                      {opp.status === 'called' && (
                        <button
                          className="rm-btn-sm rm-btn-success"
                          onClick={() => handleMarkConverted(opp.id)}
                        >
                          Convert
                        </button>
                      )}
                      {opp.status !== 'converted' && opp.status !== 'declined' && (
                        <button
                          className="rm-btn-sm rm-btn-secondary"
                          onClick={() => handleUpdateOpportunityStatus(opp.id, 'declined')}
                        >
                          Decline
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {opportunities.length === 0 && (
                  <tr>
                    <td colSpan="8" className="rm-no-data">
                      No opportunities found. Upload a rate sheet and scan to find opportunities.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Targets Tab */}
      {activeTab === 'targets' && (
        <div className="rm-targets">
          <div className="rm-filters">
            <select
              value={targetFilters.status}
              onChange={(e) => setTargetFilters({ ...targetFilters, status: e.target.value })}
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="triggered">Triggered</option>
            </select>
            <label className="rm-checkbox-label">
              <input
                type="checkbox"
                checked={targetFilters.isActive}
                onChange={(e) => setTargetFilters({ ...targetFilters, isActive: e.target.checked })}
              />
              Active Only
            </label>
          </div>

          <div className="rm-table-container">
            <table className="rm-table">
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Target Type</th>
                  <th>Threshold</th>
                  <th>Status</th>
                  <th>Auto-Call</th>
                  <th>Triggers</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {targets.map(target => (
                  <tr key={target.id} className={!target.is_active ? 'rm-inactive-row' : ''}>
                    <td>
                      <span
                        className="rm-client-link"
                        onClick={() => handleViewMumClient(target.mum_client_id)}
                      >
                        {target.client_name || `Client #${target.mum_client_id}`}
                      </span>
                      {target.client_rate && (
                        <div className="rm-client-rate-info">
                          Current: {formatRate(target.client_rate)}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="rm-target-type">{(target.target_type || '').replace(/_/g, ' ')}</span>
                    </td>
                    <td>{target.threshold_description}</td>
                    <td>
                      <span className={`rm-status-badge ${target.status}`}>
                        {target.status}
                      </span>
                    </td>
                    <td>
                      <span className={`rm-auto-badge ${target.auto_call_enabled ? 'enabled' : 'disabled'}`}>
                        {target.auto_call_enabled ? 'On' : 'Off'}
                      </span>
                    </td>
                    <td>{target.trigger_count || 0}</td>
                    <td className="rm-actions">
                      <button
                        className="rm-btn-icon"
                        onClick={() => handleToggleActive(target)}
                        title={target.is_active ? 'Pause' : 'Activate'}
                      >
                        {target.is_active ? 'Pause' : 'Start'}
                      </button>
                      <button
                        className="rm-btn-icon"
                        onClick={() => handleEditTarget(target)}
                        title="Edit"
                      >
                        Edit
                      </button>
                      <button
                        className="rm-btn-icon delete"
                        onClick={() => handleDeleteTarget(target.id)}
                        title="Delete"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {targets.length === 0 && (
                  <tr>
                    <td colSpan="7" className="rm-no-data">
                      No rate targets found. Click "New Rate Target" to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="rm-alerts">
          <div className="rm-filters">
            <select
              value={alertFilters.status}
              onChange={(e) => setAlertFilters({ ...alertFilters, status: e.target.value })}
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="called">Called</option>
              <option value="converted">Converted</option>
              <option value="dismissed">Dismissed</option>
            </select>
            <select
              value={alertFilters.priority}
              onChange={(e) => setAlertFilters({ ...alertFilters, priority: e.target.value })}
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="rm-alerts-list">
            {alerts.map(alert => (
              <div key={alert.id} className={`rm-alert-card ${getPriorityClass(alert.priority)}`}>
                <div className="rm-alert-header">
                  <div className="rm-alert-client">
                    <h4
                      className="rm-client-link"
                      onClick={() => handleViewMumClient(alert.mum_client_id)}
                    >
                      {alert.client_name || `Client #${alert.mum_client_id}`}
                    </h4>
                    <span className={`rm-priority-badge ${getPriorityClass(alert.priority)}`}>
                      {alert.priority}
                    </span>
                    <span className={`rm-status-badge ${getStatusClass(alert.status)}`}>
                      {alert.status}
                    </span>
                  </div>
                  <div className="rm-alert-date">
                    {new Date(alert.created_at).toLocaleDateString()}
                  </div>
                </div>

                <div className="rm-alert-body">
                  <div className="rm-rate-comparison">
                    <div className="rm-rate-item">
                      <span className="label">Current Rate:</span>
                      <span className="value">{formatRate(alert.client_rate)}</span>
                    </div>
                    <div className="rm-rate-arrow">→</div>
                    <div className="rm-rate-item">
                      <span className="label">Market Rate:</span>
                      <span className="value highlight">{formatRate(alert.market_rate)}</span>
                    </div>
                  </div>

                  <div className="rm-savings-info">
                    <div className="rm-savings-item">
                      <span className="label">Monthly Savings:</span>
                      <span className="value">{formatCurrency(alert.monthly_savings)}</span>
                    </div>
                    <div className="rm-savings-item">
                      <span className="label">Annual Savings:</span>
                      <span className="value">{formatCurrency(alert.annual_savings)}</span>
                    </div>
                  </div>

                  {alert.call_status && (
                    <div className="rm-call-status">
                      <span className="label">Call Status:</span>
                      <span className={`value ${alert.call_status}`}>
                        {alert.call_status}
                      </span>
                      {alert.call_outcome && (
                        <span className="rm-call-outcome"> - {alert.call_outcome}</span>
                      )}
                    </div>
                  )}
                </div>

                <div className="rm-alert-actions">
                  {alert.status === 'pending' && (
                    <>
                      <button
                        className="rm-btn-primary"
                        onClick={() => handleInitiateCall(alert.id)}
                      >
                        Initiate Call
                      </button>
                      <button
                        className="rm-btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'acknowledged')}
                      >
                        Acknowledge
                      </button>
                    </>
                  )}
                  {alert.status === 'acknowledged' && (
                    <>
                      <button
                        className="rm-btn-primary"
                        onClick={() => handleInitiateCall(alert.id)}
                      >
                        Initiate Call
                      </button>
                      <button
                        className="rm-btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'dismissed')}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                  {alert.status === 'called' && (
                    <>
                      <button
                        className="rm-btn-success"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'converted')}
                      >
                        Mark Converted
                      </button>
                      <button
                        className="rm-btn-secondary"
                        onClick={() => handleUpdateAlertStatus(alert.id, 'dismissed')}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                  <button
                    className="rm-btn-link"
                    onClick={() => handleViewMumClient(alert.mum_client_id)}
                  >
                    View Client
                  </button>
                </div>
              </div>
            ))}
            {alerts.length === 0 && (
              <div className="rm-empty-state">
                No alerts found matching your filters.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Target Modal */}
      {showTargetModal && (
        <RateTargetModal
          target={editingTarget}
          onSave={handleSaveTarget}
          onClose={() => setShowTargetModal(false)}
        />
      )}
    </div>
  );
}

export default RateMonitor;
