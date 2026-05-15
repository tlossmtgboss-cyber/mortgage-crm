import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import './PartnerROIDashboard.css';

const PartnerROIDashboard = () => {
  const navigate = useNavigate();
  const [partners, setPartners] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortBy, setSortBy] = useState('revenue_per_hour');
  const [expandedPartner, setExpandedPartner] = useState(null);

  useEffect(() => {
    fetchPartnerROI();
  }, []);

  const fetchPartnerROI = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/v1/checkin/partners/roi');
      setPartners(response.data.partners || []);
      setSummary(response.data.summary);
    } catch (err) {
      setError('Failed to load partner ROI data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const sortedPartners = [...partners].sort((a, b) => {
    switch (sortBy) {
      case 'revenue_per_hour':
        return b.revenue_per_hour - a.revenue_per_hour;
      case 'roi_percentage':
        return b.roi_percentage - a.roi_percentage;
      case 'revenue_12m':
        return b.revenue_12m - a.revenue_12m;
      case 'leads_12m':
        return b.leads_12m - a.leads_12m;
      case 'conversion_rate':
        return b.conversion_rate - a.conversion_rate;
      default:
        return 0;
    }
  });

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getRoiColor = (roi) => {
    if (roi >= 200) return '#2D7A52';
    if (roi >= 100) return '#3b82f6';
    if (roi >= 0) return '#f59e0b';
    return '#ef4444';
  };

  if (loading) {
    return (
      <div className="partner-roi-dashboard">
        <div className="loading">Loading partner ROI data...</div>
      </div>
    );
  }

  return (
    <div className="partner-roi-dashboard">
      <header className="roi-header">
        <div className="header-content">
          <h1>Partner ROI Dashboard</h1>
          <p>Track your referral partner performance and time investment</p>
        </div>
        <div className="header-actions">
          <button className="checkin-btn" onClick={() => navigate('/checkin')}>
            ☀️ Morning Check-in
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      {summary && (
        <div className="summary-cards">
          <div className="summary-card">
            <span className="card-value">{summary.total_partners}</span>
            <span className="card-label">Total Partners</span>
          </div>
          <div className="summary-card">
            <span className="card-value">{formatCurrency(summary.total_revenue_12m)}</span>
            <span className="card-label">Revenue (12m)</span>
          </div>
          <div className="summary-card">
            <span className="card-value">{summary.total_hours_invested?.toFixed(0) || 0}h</span>
            <span className="card-label">Hours Invested</span>
          </div>
          <div className="summary-card highlight">
            <span className="card-value">{summary.top_performer || '—'}</span>
            <span className="card-label">Top Performer</span>
          </div>
        </div>
      )}

      <div className="partners-section">
        <div className="section-header">
          <h2>Partner Performance</h2>
          <div className="sort-controls">
            <label>Sort by:</label>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="revenue_per_hour">$/Hour</option>
              <option value="roi_percentage">ROI %</option>
              <option value="revenue_12m">Revenue</option>
              <option value="leads_12m">Leads</option>
              <option value="conversion_rate">Conversion Rate</option>
            </select>
          </div>
        </div>

        {sortedPartners.length === 0 ? (
          <div className="empty-state">
            <p>No partner data yet. Start logging interactions in your morning check-in!</p>
            <button className="primary-btn" onClick={() => navigate('/checkin')}>
              Start Check-in
            </button>
          </div>
        ) : (
          <div className="partners-list">
            {sortedPartners.map((partner) => (
              <div
                key={partner.id}
                className={`partner-card ${expandedPartner === partner.id ? 'expanded' : ''}`}
                onClick={() => setExpandedPartner(expandedPartner === partner.id ? null : partner.id)}
              >
                <div className="partner-main">
                  <div className="partner-info">
                    <h3>{partner.name}</h3>
                    {partner.company && <span className="company">{partner.company}</span>}
                    <span className="partner-type">{partner.partner_type}</span>
                  </div>

                  <div className="partner-metrics">
                    <div className="metric">
                      <span className="metric-value" style={{ color: getRoiColor(partner.roi_percentage) }}>
                        {partner.roi_percentage > 0 ? '+' : ''}{partner.roi_percentage}%
                      </span>
                      <span className="metric-label">ROI</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{formatCurrency(partner.revenue_per_hour)}</span>
                      <span className="metric-label">$/Hour</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{partner.leads_12m}</span>
                      <span className="metric-label">Leads (12m)</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{partner.conversion_rate}%</span>
                      <span className="metric-label">Conversion</span>
                    </div>
                  </div>
                </div>

                {expandedPartner === partner.id && (
                  <div className="partner-details">
                    <div className="details-grid">
                      <div className="detail-item">
                        <span className="detail-label">Total Leads</span>
                        <span className="detail-value">{partner.total_leads}</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Converted</span>
                        <span className="detail-value">{partner.converted}</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Active Pipeline</span>
                        <span className="detail-value">{partner.active_leads} leads</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Pipeline Value</span>
                        <span className="detail-value">{formatCurrency(partner.pipeline_value)}</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Revenue (12m)</span>
                        <span className="detail-value">{formatCurrency(partner.revenue_12m)}</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Hours Invested</span>
                        <span className="detail-value">{partner.hours_invested?.toFixed(1)}h</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Time Cost</span>
                        <span className="detail-value">{formatCurrency(partner.time_cost)}</span>
                      </div>
                      <div className="detail-item">
                        <span className="detail-label">Net Profit</span>
                        <span className="detail-value" style={{ color: partner.net_profit >= 0 ? '#2D7A52' : '#ef4444' }}>
                          {formatCurrency(partner.net_profit)}
                        </span>
                      </div>
                    </div>

                    {partner.last_contact && (
                      <div className="last-contact">
                        Last contact: {new Date(partner.last_contact).toLocaleDateString()}
                      </div>
                    )}

                    <div className="partner-actions">
                      <button onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/referral-partners/${partner.id}`);
                      }}>
                        View Partner Details
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default PartnerROIDashboard;
