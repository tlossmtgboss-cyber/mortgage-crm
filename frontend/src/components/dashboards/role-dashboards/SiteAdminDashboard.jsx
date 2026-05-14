import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchWithAuth, formatCurrency } from './utils';

export const SiteAdminDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    team: { total: 0, active: 0 },
    production: { ytd: 0, volume: 0 },
    pipeline: { total: 0, volume: 0 },
    subscription: { plan: 'Professional', status: 'Active', users: 0, maxUsers: 10 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');
      setData({
        team: {
          total: result.team_stats?.total_members || 0,
          active: result.team_stats?.active_today || 0
        },
        production: {
          ytd: result.production?.yearlyActual || 0,
          volume: result.production?.yearlyVolume || 0
        },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0
        },
        subscription: {
          plan: 'Professional', status: 'Active',
          users: result.team_stats?.total_members || 0,
          maxUsers: 25
        }
      });
    } catch (error) {
      console.error('Failed to load Site Admin dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard site-admin-dashboard">
      <div className="dashboard-header">
        <h1>Site Administrator</h1>
        <p className="subtitle">Company account management and settings</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/team-members')}>
          <div className="kpi-icon">&#x1F465;</div>
          <div className="kpi-content">
            <div className="kpi-label">Team Members</div>
            <div className="kpi-value">{data.team.total}</div>
            <div className="kpi-subtext">{data.team.active} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/scorecard')}>
          <div className="kpi-icon">&#x1F4CA;</div>
          <div className="kpi-content">
            <div className="kpi-label">YTD Production</div>
            <div className="kpi-value">{data.production.ytd} units</div>
            <div className="kpi-subtext">{formatCurrency(data.production.volume)}</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans')}>
          <div className="kpi-icon">&#x1F3E0;</div>
          <div className="kpi-content">
            <div className="kpi-label">Active Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className="kpi-card success" onClick={() => navigate('/settings/subscription')}>
          <div className="kpi-icon">&#x1F4B3;</div>
          <div className="kpi-content">
            <div className="kpi-label">Subscription</div>
            <div className="kpi-value">{data.subscription.plan}</div>
            <div className="kpi-subtext">{data.subscription.users}/{data.subscription.maxUsers} users</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section">
          <div className="section-header">
            <h2>Account Management</h2>
          </div>
          <div className="quick-actions-grid">
            <button className="quick-action-card" onClick={() => navigate('/team-members')}>
              <span className="action-icon">&#x1F464;</span>
              <span className="action-label">Manage Users</span>
              <span className="action-desc">Add, edit, or remove team members</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/subscription')}>
              <span className="action-icon">&#x1F4B3;</span>
              <span className="action-label">Subscription & Billing</span>
              <span className="action-desc">Manage your plan and payments</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/company')}>
              <span className="action-icon">&#x1F3E2;</span>
              <span className="action-label">Company Settings</span>
              <span className="action-desc">Logo, branding, and company info</span>
            </button>
            <button className="quick-action-card" onClick={() => navigate('/settings/integrations')}>
              <span className="action-icon">&#x1F517;</span>
              <span className="action-label">Integrations</span>
              <span className="action-desc">Connect external services</span>
            </button>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <h2>Team Overview</h2>
            <button className="view-all-btn" onClick={() => navigate('/team-members')}>View All →</button>
          </div>
          <div className="team-summary">
            <div className="summary-stat">
              <span className="stat-label">Total Users</span>
              <span className="stat-value">{data.team.total}</span>
            </div>
            <div className="summary-stat">
              <span className="stat-label">Active Today</span>
              <span className="stat-value">{data.team.active}</span>
            </div>
            <div className="summary-stat">
              <span className="stat-label">Available Seats</span>
              <span className="stat-value">{data.subscription.maxUsers - data.subscription.users}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
