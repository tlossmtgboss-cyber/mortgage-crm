import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { dashboardAPI } from '../services/api';
import './Dashboard.css';

function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const data = await dashboardAPI.getDashboard();
      setStats(data);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const modules = [
    {
      id: 'leads',
      title: 'Leads',
      description: 'Manage and track new prospects',
      icon: '👥',
      path: '/leads',
    },
    {
      id: 'loans',
      title: 'Active Loans',
      description: 'Monitor in-process loans',
      icon: '💼',
      path: '/loans',
    },
    {
      id: 'portfolio',
      title: 'Portfolio',
      description: 'View closed client relationships',
      icon: '📊',
      path: '/portfolio',
    },
    {
      id: 'tasks',
      title: 'Tasks',
      description: 'Automated task management',
      icon: '✓',
      path: '/tasks',
    },
    {
      id: 'calendar',
      title: 'Calendar',
      description: 'Schedule appointments and events',
      icon: '📅',
      path: '/calendar',
    },
    {
      id: 'scorecard',
      title: 'Scorecard',
      description: 'Performance metrics and analytics',
      icon: '📈',
      path: '/scorecard',
    },
    {
      id: 'assistant',
      title: 'AI Assistant',
      description: 'Your intelligent CRM copilot',
      icon: '🤖',
      path: '/assistant',
    },
  ];

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Welcome to your AI-Powered Mortgage CRM</p>
      </div>

      {loading ? (
        <div className="loading">Loading dashboard...</div>
      ) : stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon">👥</div>
            <div className="stat-content">
              <h3>{stats.stats?.total_leads || 0}</h3>
              <p>Total Leads</p>
              {stats.stats?.hot_leads > 0 && (
                <span className="stat-badge">{stats.stats.hot_leads} hot leads</span>
              )}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">💼</div>
            <div className="stat-content">
              <h3>{stats.stats?.active_loans || 0}</h3>
              <p>Active Loans</p>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">💰</div>
            <div className="stat-content">
              <h3>${((stats.stats?.pipeline_volume || 0) / 1000000).toFixed(1)}M</h3>
              <p>Pipeline Volume</p>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">📈</div>
            <div className="stat-content">
              <h3>{stats.stats?.conversion_rate || 0}%</h3>
              <p>Conversion Rate</p>
            </div>
          </div>
        </div>
      )}

      <div className="modules-grid">
        {modules.map((module) => (
          <div
            key={module.id}
            className="module-card"
            onClick={() => navigate(module.path)}
          >
            <div className="module-icon">{module.icon}</div>
            <div className="module-content">
              <h3>{module.title}</h3>
              <p>{module.description}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="ai-tips">
        <div className="tip-box">
          <h4>AI Assistant Tips</h4>
          <ul>
            <li>Click the "AI Assistant" button in the navigation to get help with any task</li>
            <li>The AI can help you schedule appointments, manage leads, and automate follow-ups</li>
            <li>Ask the AI to analyze your performance metrics and provide insights</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
