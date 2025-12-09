import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import './LODashboard.css';

/**
 * LODashboard - Loan Officer Dashboard with Social Automation
 *
 * Features:
 * - Pipeline overview
 * - Application management
 * - AI-generated social media content
 * - Quick actions
 * - Performance metrics
 */

const LODashboard = () => {
  const navigate = useNavigate();

  // Dashboard state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  const [applications, setApplications] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);

  // Social content state
  const [socialContent, setSocialContent] = useState([]);
  const [generatingSocial, setGeneratingSocial] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState('all');

  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Load dashboard data
  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch multiple endpoints in parallel
      const [statsRes, appsRes, activityRes] = await Promise.all([
        api.get('/api/v1/lo/dashboard/stats'),
        api.get('/api/v1/lo/applications'),
        api.get('/api/v1/lo/activity'),
      ]);

      setStats(statsRes.data);
      setApplications(appsRes.data.applications || []);
      setRecentActivity(activityRes.data.activities || []);

    } catch (err) {
      console.error('Dashboard load error:', err);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // Generate AI social content
  const generateSocialContent = async (contentType) => {
    setGeneratingSocial(true);
    try {
      const res = await api.post('/api/v1/lo/social/generate', {
        type: contentType,
        platform: selectedPlatform,
      });
      setSocialContent(res.data.content || []);
    } catch (err) {
      console.error('Social content generation error:', err);
    } finally {
      setGeneratingSocial(false);
    }
  };

  // Copy social content to clipboard
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    // Could show a toast notification here
  };

  // Filter applications
  const filteredApplications = applications.filter(app => {
    const matchesStatus = statusFilter === 'all' || app.status === statusFilter;
    const matchesSearch = searchTerm === '' ||
      `${app.borrower_first_name} ${app.borrower_last_name}`.toLowerCase().includes(searchTerm.toLowerCase()) ||
      app.id.toString().includes(searchTerm);
    return matchesStatus && matchesSearch;
  });

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount || 0);
  };

  // Format date
  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  // Get status badge class
  const getStatusClass = (status) => {
    const statusMap = {
      'pending': 'pending',
      'in_progress': 'progress',
      'submitted': 'submitted',
      'under_review': 'review',
      'approved': 'approved',
      'denied': 'denied',
      'funded': 'funded',
    };
    return statusMap[status] || 'default';
  };

  if (loading) {
    return (
      <div className="lo-dashboard-loading">
        <div className="loading-spinner"></div>
        <p>Loading your dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="lo-dashboard-error">
        <div className="error-icon">⚠️</div>
        <h2>Unable to load dashboard</h2>
        <p>{error}</p>
        <button onClick={loadDashboard}>Try Again</button>
      </div>
    );
  }

  return (
    <div className="lo-dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <h1>Dashboard</h1>
          <p className="header-date">{new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
          })}</p>
        </div>
        <div className="header-right">
          <button className="btn-new-app" onClick={() => navigate('/applications/new')}>
            + New Application
          </button>
        </div>
      </header>

      {/* Stats Cards */}
      <section className="stats-section">
        <div className="stats-grid">
          <div className="stat-card primary">
            <div className="stat-icon">📊</div>
            <div className="stat-content">
              <span className="stat-value">{stats?.pipeline_count || 0}</span>
              <span className="stat-label">Active Pipeline</span>
            </div>
          </div>
          <div className="stat-card success">
            <div className="stat-icon">💰</div>
            <div className="stat-content">
              <span className="stat-value">{formatCurrency(stats?.pipeline_volume)}</span>
              <span className="stat-label">Pipeline Volume</span>
            </div>
          </div>
          <div className="stat-card warning">
            <div className="stat-icon">⏳</div>
            <div className="stat-content">
              <span className="stat-value">{stats?.pending_review || 0}</span>
              <span className="stat-label">Pending Review</span>
            </div>
          </div>
          <div className="stat-card info">
            <div className="stat-icon">📅</div>
            <div className="stat-content">
              <span className="stat-value">{stats?.calls_today || 0}</span>
              <span className="stat-label">Calls Today</span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content */}
      <div className="dashboard-content">
        {/* Applications List */}
        <section className="applications-section">
          <div className="section-header">
            <h2>Applications</h2>
            <div className="section-actions">
              <div className="search-box">
                <input
                  type="text"
                  placeholder="Search applications..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="all">All Status</option>
                <option value="pending">Pending</option>
                <option value="in_progress">In Progress</option>
                <option value="submitted">Submitted</option>
                <option value="under_review">Under Review</option>
                <option value="approved">Approved</option>
              </select>
            </div>
          </div>

          <div className="applications-list">
            {filteredApplications.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">📋</span>
                <p>No applications found</p>
              </div>
            ) : (
              filteredApplications.map(app => (
                <div
                  key={app.id}
                  className="application-card"
                  onClick={() => navigate(`/applications/${app.id}`)}
                >
                  <div className="app-main">
                    <div className="app-borrower">
                      <span className="borrower-name">
                        {app.borrower_first_name} {app.borrower_last_name}
                      </span>
                      <span className="app-id">#{app.id}</span>
                    </div>
                    <div className="app-details">
                      <span className="app-amount">{formatCurrency(app.loan_amount)}</span>
                      <span className="app-purpose">{app.loan_purpose || 'Purchase'}</span>
                    </div>
                  </div>
                  <div className="app-meta">
                    <span className={`status-badge ${getStatusClass(app.status)}`}>
                      {app.status?.replace('_', ' ')}
                    </span>
                    <span className="app-date">{formatDate(app.updated_at)}</span>
                  </div>
                  <div className="app-actions">
                    <button className="btn-icon" title="Send reminder">📧</button>
                    <button className="btn-icon" title="Schedule call">📞</button>
                    <button className="btn-icon" title="Export MISMO">📄</button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Sidebar */}
        <aside className="dashboard-sidebar">
          {/* Quick Actions */}
          <div className="sidebar-card">
            <h3>Quick Actions</h3>
            <div className="quick-actions">
              <button onClick={() => navigate('/applications/new')}>
                <span className="action-icon">➕</span>
                <span>New Application</span>
              </button>
              <button onClick={() => navigate('/leads')}>
                <span className="action-icon">👥</span>
                <span>View Leads</span>
              </button>
              <button onClick={() => navigate('/calendar')}>
                <span className="action-icon">📅</span>
                <span>Calendar</span>
              </button>
              <button onClick={() => navigate('/reports')}>
                <span className="action-icon">📊</span>
                <span>Reports</span>
              </button>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="sidebar-card">
            <h3>Recent Activity</h3>
            <div className="activity-list">
              {recentActivity.length === 0 ? (
                <p className="no-activity">No recent activity</p>
              ) : (
                recentActivity.slice(0, 5).map((activity, index) => (
                  <div key={index} className="activity-item">
                    <span className="activity-icon">
                      {activity.type === 'application' ? '📝' :
                       activity.type === 'call' ? '📞' :
                       activity.type === 'document' ? '📄' : '💬'}
                    </span>
                    <div className="activity-content">
                      <span className="activity-text">{activity.description}</span>
                      <span className="activity-time">{formatDate(activity.created_at)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Social Content Generator */}
          <div className="sidebar-card social-card">
            <h3>🤖 AI Social Content</h3>
            <p className="social-desc">
              Generate engaging social media content to grow your business.
            </p>

            <div className="platform-select">
              <select
                value={selectedPlatform}
                onChange={(e) => setSelectedPlatform(e.target.value)}
              >
                <option value="all">All Platforms</option>
                <option value="linkedin">LinkedIn</option>
                <option value="facebook">Facebook</option>
                <option value="instagram">Instagram</option>
                <option value="twitter">Twitter/X</option>
              </select>
            </div>

            <div className="content-types">
              <button
                onClick={() => generateSocialContent('market_update')}
                disabled={generatingSocial}
              >
                📈 Market Update
              </button>
              <button
                onClick={() => generateSocialContent('tip')}
                disabled={generatingSocial}
              >
                💡 Homebuyer Tip
              </button>
              <button
                onClick={() => generateSocialContent('rate_alert')}
                disabled={generatingSocial}
              >
                🔔 Rate Alert
              </button>
              <button
                onClick={() => generateSocialContent('success_story')}
                disabled={generatingSocial}
              >
                🏆 Success Story
              </button>
            </div>

            {generatingSocial && (
              <div className="generating">
                <div className="loading-spinner small"></div>
                <span>Generating content...</span>
              </div>
            )}

            {socialContent.length > 0 && (
              <div className="generated-content">
                {socialContent.map((content, index) => (
                  <div key={index} className="content-item">
                    <div className="content-platform">{content.platform}</div>
                    <p className="content-text">{content.text}</p>
                    {content.hashtags && (
                      <p className="content-hashtags">{content.hashtags}</p>
                    )}
                    <div className="content-actions">
                      <button onClick={() => copyToClipboard(content.text + '\n\n' + (content.hashtags || ''))}>
                        Copy
                      </button>
                      <button>Schedule</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
};

export default LODashboard;
