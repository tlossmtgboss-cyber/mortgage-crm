import React, { useState, useEffect } from 'react';
import { dashboardAPI } from '../services/api';
import './Dashboard.css';

function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const dashboardData = await dashboardAPI.getDashboard();
      setData(dashboardData);
    } catch (err) {
      setError('Failed to load dashboard');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading dashboard...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  const { user, stats, recent_leads, recent_loans } = data || {};

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Welcome back, {user?.name || 'User'}!</h1>
        <p className="subtitle">Here's what's happening with your pipeline today</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon" style={{ background: '#667eea' }}>📊</div>
          <div className="stat-content">
            <h3>{stats?.total_leads || 0}</h3>
            <p>Total Leads</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: '#f093fb' }}>🔥</div>
          <div className="stat-content">
            <h3>{stats?.hot_leads || 0}</h3>
            <p>Hot Leads</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: '#4facfe' }}>💼</div>
          <div className="stat-content">
            <h3>{stats?.active_loans || 0}</h3>
            <p>Active Loans</p>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: '#43e97b' }}>💰</div>
          <div className="stat-content">
            <h3>${(stats?.pipeline_volume || 0).toLocaleString()}</h3>
            <p>Pipeline Volume</p>
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-section">
          <h2>Recent Leads</h2>
          <div className="items-list">
            {recent_leads && recent_leads.length > 0 ? (
              recent_leads.map((lead) => (
                <div key={lead.id} className="item-card">
                  <div className="item-header">
                    <h3>{lead.name}</h3>
                    <span className={`badge badge-${getScoreColor(lead.ai_score)}`}>
                      Score: {lead.ai_score}
                    </span>
                  </div>
                  <div className="item-details">
                    <span className="stage-badge">{lead.stage}</span>
                    <span className="date">
                      {new Date(lead.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <p className="empty-state">No recent leads</p>
            )}
          </div>
        </div>

        <div className="dashboard-section">
          <h2>Recent Loans</h2>
          <div className="items-list">
            {recent_loans && recent_loans.length > 0 ? (
              recent_loans.map((loan) => (
                <div key={loan.id} className="item-card">
                  <div className="item-header">
                    <h3>{loan.borrower}</h3>
                    <span className="loan-number">{loan.loan_number}</span>
                  </div>
                  <div className="item-details">
                    <span className="stage-badge">{loan.stage}</span>
                    <span className="amount">${loan.amount.toLocaleString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="empty-state">No recent loans</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function getScoreColor(score) {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warning';
  return 'danger';
}

export default Dashboard;
