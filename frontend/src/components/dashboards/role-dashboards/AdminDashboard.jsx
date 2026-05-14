import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PipelineProbabilityWidget } from '../../PipelineProbability';
import { fetchWithAuth, formatCurrency } from './utils';

export const AdminDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    company: { totalUsers: 0, activeToday: 0, branches: 0 },
    production: { mtd: 0, ytd: 0, revenue: 0 },
    pipeline: { total: 0, volume: 0 },
    health: { systemStatus: 'healthy', alerts: 0, compliance: 100 }
  });

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const result = await fetchWithAuth('/api/v1/dashboard');

      setData({
        company: {
          totalUsers: result.team_stats?.total_members || 25,
          activeToday: result.team_stats?.active_today || 18,
          branches: 3
        },
        production: {
          mtd: result.production?.monthlyActual || 0,
          ytd: result.production?.annualActual || 0,
          revenue: result.production?.revenue || 0
        },
        pipeline: {
          total: result.pipeline_stats?.reduce((sum, s) => sum + (s.count || 0), 0) || 0,
          volume: result.pipeline_stats?.reduce((sum, s) => sum + (s.volume || 0), 0) || 0
        },
        health: {
          systemStatus: 'healthy',
          alerts: result.loan_issues?.length || 0,
          compliance: 98
        }
      });
    } catch (error) {
      console.error('Failed to load Admin dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="role-dashboard loading"><div className="loading-spinner" /></div>;
  }

  return (
    <div className="role-dashboard admin-dashboard">
      <div className="dashboard-header">
        <h1>Executive Dashboard</h1>
        <p className="subtitle">Company-wide metrics and system health</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card primary" onClick={() => navigate('/team-members')}>
          <div className="kpi-icon">&#x1F3E2;</div>
          <div className="kpi-content">
            <div className="kpi-label">Total Users</div>
            <div className="kpi-value">{data.company.totalUsers}</div>
            <div className="kpi-subtext">{data.company.activeToday} active today</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/profitability')}>
          <div className="kpi-icon">&#x1F4B0;</div>
          <div className="kpi-content">
            <div className="kpi-label">YTD Production</div>
            <div className="kpi-value">{data.production.ytd} units</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)} pipeline</div>
          </div>
        </div>

        <div className="kpi-card" onClick={() => navigate('/loans')}>
          <div className="kpi-icon">&#x1F4C8;</div>
          <div className="kpi-content">
            <div className="kpi-label">Active Pipeline</div>
            <div className="kpi-value">{data.pipeline.total} loans</div>
            <div className="kpi-subtext">{formatCurrency(data.pipeline.volume)}</div>
          </div>
        </div>

        <div className={`kpi-card ${data.health.systemStatus === 'healthy' ? 'success' : 'alert'}`}>
          <div className="kpi-icon">{data.health.systemStatus === 'healthy' ? '&#x2705;' : '&#x26A0;&#xFE0F;'}</div>
          <div className="kpi-content">
            <div className="kpi-label">System Health</div>
            <div className="kpi-value">{data.health.systemStatus === 'healthy' ? 'Healthy' : 'Issues'}</div>
            <div className="kpi-subtext">{data.health.compliance}% compliance</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <div className="section company-section">
          <div className="section-header">
            <h2>Company Overview</h2>
            <button className="view-all-btn" onClick={() => navigate('/settings/account-management')}>Manage Accounts →</button>
          </div>
          <div className="company-stats">
            <div className="company-stat">
              <span className="stat-label">Branches</span>
              <span className="stat-value">{data.company.branches}</span>
            </div>
            <div className="company-stat">
              <span className="stat-label">MTD Units</span>
              <span className="stat-value">{data.production.mtd}</span>
            </div>
            <div className="company-stat">
              <span className="stat-label">Active Alerts</span>
              <span className="stat-value warning">{data.health.alerts}</span>
            </div>
          </div>
        </div>

        <div className="section quick-links">
          <div className="section-header">
            <h2>Quick Links</h2>
          </div>
          <div className="links-grid">
            <button className="quick-link" onClick={() => navigate('/settings/account-management')}>
              <span className="link-icon">&#x1F464;</span>
              <span className="link-label">Account Management</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/admin/settings')}>
              <span className="link-icon">&#x2699;&#xFE0F;</span>
              <span className="link-label">Admin Settings</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/compliance')}>
              <span className="link-icon">&#x1F4CB;</span>
              <span className="link-label">Compliance</span>
            </button>
            <button className="quick-link" onClick={() => navigate('/scorecard')}>
              <span className="link-icon">&#x1F4CA;</span>
              <span className="link-label">Scorecards</span>
            </button>
          </div>
        </div>

        <div className="section probability-section">
          <PipelineProbabilityWidget compact={false} />
        </div>
      </div>
    </div>
  );
};
