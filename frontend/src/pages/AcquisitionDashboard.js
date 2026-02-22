import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { acquisitionAPI } from '../services/acquisitionApi';
import './AcquisitionDashboard.css';
import { toast } from '../utils/toast';

function AcquisitionDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Dashboard data
  const [dashboard, setDashboard] = useState(null);
  const [speedToLead, setSpeedToLead] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [blueprints, setBlueprints] = useState([]);

  // Launch modal
  const [showLaunchModal, setShowLaunchModal] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launchForm, setLaunchForm] = useState({
    goal_type: 'PURCHASE_BUYERS',
    budget_type: 'DAILY',
    budget_amount: 100,
    market_geo: { state: '', metro: '' },
    product_focus: 'PURCHASE',
    capacity_leads_per_week: 10,
    name: '',
    blueprint_id: null,
  });

  // Fetch all dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      setError(null);
      const [dashboardData, stlData, funnelData, blueprintData] = await Promise.all([
        acquisitionAPI.getDashboard(),
        acquisitionAPI.getSpeedToLeadMetrics(),
        acquisitionAPI.getFunnelMetrics(),
        acquisitionAPI.getBlueprints(),
      ]);

      setDashboard(dashboardData);
      setSpeedToLead(stlData);
      setFunnel(funnelData);
      setBlueprints(blueprintData);
      setLoading(false);
      setRefreshing(false);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
      setError('Failed to load acquisition dashboard. Please try again.');
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();

    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchDashboardData, 60000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboardData();
  };

  const handleLaunchCampaign = async () => {
    try {
      setLaunching(true);
      await acquisitionAPI.launchCampaign(launchForm);
      setShowLaunchModal(false);
      setLaunchForm({
        goal_type: 'PURCHASE_BUYERS',
        budget_type: 'DAILY',
        budget_amount: 100,
        market_geo: { state: '', metro: '' },
        product_focus: 'PURCHASE',
        capacity_leads_per_week: 10,
        name: '',
        blueprint_id: null,
      });
      fetchDashboardData();
    } catch (err) {
      console.error('Error launching campaign:', err);
      toast.error('Failed to launch campaign. Please try again.');
    } finally {
      setLaunching(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount || 0);
  };

  const formatNumber = (num) => {
    return new Intl.NumberFormat('en-US').format(num || 0);
  };

  const getSTLClass = (rate) => {
    if (rate >= 90) return 'good';
    if (rate >= 70) return 'warning';
    return 'critical';
  };

  if (loading) {
    return (
      <div className="acquisition-dashboard loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Acquisition Dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="acquisition-dashboard">
        <div className="dashboard-header">
          <div className="header-left">
            <h1><i className="fas fa-rocket"></i> Client Acquisition</h1>
            <p className="subtitle">One-button campaign launch with full attribution</p>
          </div>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={fetchDashboardData}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  const maxFunnelValue = Math.max(
    funnel?.funnel?.leads || 0,
    funnel?.funnel?.meetings || 0,
    funnel?.funnel?.applications || 0,
    funnel?.funnel?.funded || 0,
    1
  );

  return (
    <div className="acquisition-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-left">
          <h1><i className="fas fa-rocket"></i> Client Acquisition</h1>
          <p className="subtitle">One-button campaign launch with full attribution</p>
        </div>
        <div className="header-actions">
          <button
            className={`refresh-btn ${refreshing ? 'spinning' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <i className="fas fa-sync-alt"></i>
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <button className="launch-btn" onClick={() => setShowLaunchModal(true)}>
            <i className="fas fa-play"></i> Launch Campaign
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon blue">
            <i className="fas fa-bullhorn"></i>
          </div>
          <div className="stat-content">
            <div className="label">Active Campaigns</div>
            <div className="value">{dashboard?.active_campaigns || 0}</div>
            <div className="change neutral">of {dashboard?.total_campaigns || 0} total</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon green">
            <i className="fas fa-users"></i>
          </div>
          <div className="stat-content">
            <div className="label">Total Leads</div>
            <div className="value">{formatNumber(dashboard?.total_leads)}</div>
            <div className="change positive">
              <i className="fas fa-arrow-up"></i> Active pipeline
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon purple">
            <i className="fas fa-calendar-check"></i>
          </div>
          <div className="stat-content">
            <div className="label">Meetings Booked</div>
            <div className="value">{formatNumber(dashboard?.total_meetings)}</div>
            <div className="change neutral">
              {funnel?.conversion_rates?.lead_to_meeting || 0}% conversion
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon orange">
            <i className="fas fa-file-signature"></i>
          </div>
          <div className="stat-content">
            <div className="label">Applications</div>
            <div className="value">{formatNumber(dashboard?.total_applications)}</div>
            <div className="change neutral">
              {funnel?.conversion_rates?.meeting_to_application || 0}% conversion
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon teal">
            <i className="fas fa-home"></i>
          </div>
          <div className="stat-content">
            <div className="label">Loans Funded</div>
            <div className="value">{formatNumber(dashboard?.total_funded)}</div>
            <div className="change positive">
              <i className="fas fa-dollar-sign"></i> {formatCurrency(dashboard?.total_revenue)}
            </div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon pink">
            <i className="fas fa-bolt"></i>
          </div>
          <div className="stat-content">
            <div className="label">Speed-to-Lead</div>
            <div className="value">{dashboard?.speed_to_lead_compliance || 0}%</div>
            <div className={`change ${getSTLClass(dashboard?.speed_to_lead_compliance)}`}>
              <i className={`fas ${dashboard?.speed_to_lead_compliance >= 90 ? 'fa-check' : 'fa-clock'}`}></i>
              {dashboard?.speed_to_lead_compliance >= 90 ? 'On target' : 'Needs attention'}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="main-content">
        {/* Left Column */}
        <div className="left-column">
          {/* Campaigns */}
          <div className="card">
            <div className="card-header">
              <h2><i className="fas fa-bullhorn"></i> Active Campaigns</h2>
              <a href="/acquisition/campaigns" className="view-all-link">
                View All <i className="fas fa-arrow-right"></i>
              </a>
            </div>
            <div className="card-content">
              {dashboard?.campaigns?.length > 0 ? (
                <div className="campaigns-list">
                  {dashboard.campaigns.slice(0, 5).map((campaign) => (
                    <div
                      key={campaign.id}
                      className="campaign-item"
                      onClick={() => navigate(`/acquisition/campaign/${campaign.id}`)}
                    >
                      <div className="campaign-info">
                        <div className="campaign-name">
                          {campaign.name || `${campaign.goal_type} Campaign`}
                          <span className={`status-badge ${campaign.status?.toLowerCase()}`}>
                            {campaign.status}
                          </span>
                        </div>
                        <div className="campaign-meta">
                          {campaign.goal_type} • {formatCurrency(campaign.budget_amount)}/
                          {campaign.budget_type?.toLowerCase()}
                        </div>
                      </div>
                      <div className="campaign-stats">
                        <div className="campaign-stat">
                          <div className="number">{campaign.leads_generated}</div>
                          <div className="label">Leads</div>
                        </div>
                        <div className="campaign-stat">
                          <div className="number">{campaign.meetings_booked}</div>
                          <div className="label">Meetings</div>
                        </div>
                        <div className="campaign-stat">
                          <div className="number">{campaign.loans_closed}</div>
                          <div className="label">Funded</div>
                        </div>
                        <div className="campaign-stat">
                          <div className="number">
                            {campaign.roi_percentage != null
                              ? `${campaign.roi_percentage.toFixed(0)}%`
                              : '-'}
                          </div>
                          <div className="label">ROI</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <i className="fas fa-bullhorn"></i>
                  <p>No campaigns yet. Launch your first campaign!</p>
                </div>
              )}
            </div>
          </div>

          {/* Funnel */}
          <div className="card">
            <div className="card-header">
              <h2><i className="fas fa-filter"></i> Conversion Funnel</h2>
              <span className="view-all-link">{funnel?.period_days || 30} days</span>
            </div>
            <div className="card-content">
              <div className="funnel-container">
                <div className="funnel-stage">
                  <div className="funnel-label">Leads</div>
                  <div className="funnel-bar-container">
                    <div
                      className="funnel-bar leads"
                      style={{ width: `${((funnel?.funnel?.leads || 0) / maxFunnelValue) * 100}%` }}
                    >
                      <span className="funnel-count">{funnel?.funnel?.leads || 0}</span>
                    </div>
                    <span className="funnel-rate">100%</span>
                  </div>
                </div>

                <div className="funnel-stage">
                  <div className="funnel-label">Meetings</div>
                  <div className="funnel-bar-container">
                    <div
                      className="funnel-bar meetings"
                      style={{ width: `${((funnel?.funnel?.meetings || 0) / maxFunnelValue) * 100}%` }}
                    >
                      <span className="funnel-count">{funnel?.funnel?.meetings || 0}</span>
                    </div>
                    <span className="funnel-rate">
                      {funnel?.conversion_rates?.lead_to_meeting || 0}%
                    </span>
                  </div>
                </div>

                <div className="funnel-stage">
                  <div className="funnel-label">Applications</div>
                  <div className="funnel-bar-container">
                    <div
                      className="funnel-bar applications"
                      style={{ width: `${((funnel?.funnel?.applications || 0) / maxFunnelValue) * 100}%` }}
                    >
                      <span className="funnel-count">{funnel?.funnel?.applications || 0}</span>
                    </div>
                    <span className="funnel-rate">
                      {funnel?.conversion_rates?.meeting_to_application || 0}%
                    </span>
                  </div>
                </div>

                <div className="funnel-stage">
                  <div className="funnel-label">Funded</div>
                  <div className="funnel-bar-container">
                    <div
                      className="funnel-bar funded"
                      style={{ width: `${((funnel?.funnel?.funded || 0) / maxFunnelValue) * 100}%` }}
                    >
                      <span className="funnel-count">{funnel?.funnel?.funded || 0}</span>
                    </div>
                    <span className="funnel-rate">
                      {funnel?.conversion_rates?.application_to_funded || 0}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="right-column">
          {/* ROI Card */}
          <div className="roi-card">
            <div className={`roi-value ${(dashboard?.overall_roi || 0) >= 0 ? 'positive' : 'negative'}`}>
              {dashboard?.overall_roi != null ? `${dashboard.overall_roi.toFixed(0)}%` : '—'}
            </div>
            <div className="roi-label">Overall Return on Investment</div>
            <div className="roi-details">
              <div className="roi-detail">
                <div className="value">{formatCurrency(dashboard?.total_spend)}</div>
                <div className="label">Total Spend</div>
              </div>
              <div className="roi-detail">
                <div className="value">{formatCurrency(dashboard?.total_revenue)}</div>
                <div className="label">Revenue</div>
              </div>
            </div>
          </div>

          {/* Temperature Distribution */}
          <div className="card">
            <div className="card-header">
              <h2><i className="fas fa-thermometer-half"></i> Lead Temperature</h2>
            </div>
            <div className="card-content">
              <div className="temperature-grid">
                <div className="temp-card hot">
                  <div className="emoji">🔥</div>
                  <div className="count">{dashboard?.temperature_distribution?.HOT || 0}</div>
                  <div className="label">Hot</div>
                </div>
                <div className="temp-card warm">
                  <div className="emoji">☀️</div>
                  <div className="count">{dashboard?.temperature_distribution?.WARM || 0}</div>
                  <div className="label">Warm</div>
                </div>
                <div className="temp-card cold">
                  <div className="emoji">❄️</div>
                  <div className="count">{dashboard?.temperature_distribution?.COLD || 0}</div>
                  <div className="label">Cold</div>
                </div>
              </div>
            </div>
          </div>

          {/* Speed-to-Lead */}
          <div className="card">
            <div className="card-header">
              <h2><i className="fas fa-bolt"></i> Speed-to-Lead</h2>
            </div>
            <div className="card-content">
              <div className="stl-metrics">
                <div className="stl-card">
                  <div className={`value ${getSTLClass(speedToLead?.compliance_rate)}`}>
                    {speedToLead?.compliance_rate?.toFixed(1) || 0}%
                  </div>
                  <div className="label">SLA Compliance</div>
                </div>
                <div className="stl-card">
                  <div className="value">
                    {speedToLead?.avg_response_time_seconds
                      ? `${Math.round(speedToLead.avg_response_time_seconds / 60)}m`
                      : '—'}
                  </div>
                  <div className="label">Avg Response</div>
                </div>
              </div>

              <div className="stl-progress">
                <div className="progress-bar">
                  <div
                    className={`progress-fill ${getSTLClass(speedToLead?.compliance_rate)}`}
                    style={{ width: `${speedToLead?.compliance_rate || 0}%` }}
                  ></div>
                </div>
                <div className="progress-label">
                  <span>{speedToLead?.within_sla || 0} within SLA</span>
                  <span>{speedToLead?.missed_sla || 0} missed</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Launch Modal */}
      {showLaunchModal && (
        <div className="modal-overlay" onClick={() => setShowLaunchModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2><i className="fas fa-rocket"></i> Launch New Campaign</h2>
              <button className="modal-close" onClick={() => setShowLaunchModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Campaign Name (optional)</label>
                <input
                  type="text"
                  placeholder="My Campaign"
                  value={launchForm.name}
                  onChange={(e) => setLaunchForm({ ...launchForm, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Campaign Goal</label>
                <div className="blueprint-grid">
                  {[
                    { id: 'PURCHASE_BUYERS', name: 'Purchase Buyers', desc: 'First-time and move-up buyers' },
                    { id: 'REFI_PROSPECTS', name: 'Refinance', desc: 'Rate & cash-out refinance' },
                    { id: 'REALTOR_PARTNERS', name: 'Realtor Partners', desc: 'Build agent relationships' },
                    { id: 'PAST_CLIENT_REACTIVATION', name: 'Past Clients', desc: 'Reactivate past database' },
                  ].map((goal) => (
                    <div
                      key={goal.id}
                      className={`blueprint-option ${launchForm.goal_type === goal.id ? 'selected' : ''}`}
                      onClick={() => setLaunchForm({ ...launchForm, goal_type: goal.id })}
                    >
                      <div className="name">{goal.name}</div>
                      <div className="description">{goal.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Budget Amount ($)</label>
                  <input
                    type="number"
                    min="10"
                    value={launchForm.budget_amount}
                    onChange={(e) => setLaunchForm({
                      ...launchForm,
                      budget_amount: parseFloat(e.target.value) || 0
                    })}
                  />
                </div>
                <div className="form-group">
                  <label>Budget Period</label>
                  <select
                    value={launchForm.budget_type}
                    onChange={(e) => setLaunchForm({ ...launchForm, budget_type: e.target.value })}
                  >
                    <option value="DAILY">Daily</option>
                    <option value="WEEKLY">Weekly</option>
                    <option value="MONTHLY">Monthly</option>
                    <option value="TOTAL">Total Budget</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Target State</label>
                  <input
                    type="text"
                    placeholder="CA"
                    maxLength={2}
                    value={launchForm.market_geo.state}
                    onChange={(e) => setLaunchForm({
                      ...launchForm,
                      market_geo: { ...launchForm.market_geo, state: e.target.value.toUpperCase() }
                    })}
                  />
                </div>
                <div className="form-group">
                  <label>Target Metro (optional)</label>
                  <input
                    type="text"
                    placeholder="San Francisco"
                    value={launchForm.market_geo.metro}
                    onChange={(e) => setLaunchForm({
                      ...launchForm,
                      market_geo: { ...launchForm.market_geo, metro: e.target.value }
                    })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Leads Per Week Capacity</label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={launchForm.capacity_leads_per_week}
                  onChange={(e) => setLaunchForm({
                    ...launchForm,
                    capacity_leads_per_week: parseInt(e.target.value) || 10
                  })}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setShowLaunchModal(false)}>
                Cancel
              </button>
              <button
                className="btn-launch"
                onClick={handleLaunchCampaign}
                disabled={launching || !launchForm.market_geo.state}
              >
                {launching ? (
                  <>
                    <i className="fas fa-spinner fa-spin"></i> Launching...
                  </>
                ) : (
                  <>
                    <i className="fas fa-rocket"></i> Launch Campaign
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AcquisitionDashboard;
