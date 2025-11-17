import React from 'react';

/**
 * ARCHIVED: Original KPIs Tab (Tab 2) - Replaced by Roles & Responsibilities
 * Date Archived: 2025-11-16
 *
 * This component was the original "KPIs" tab showing basic performance metrics.
 * It has been replaced with a comprehensive "Roles & Responsibilities" tab.
 * Kept here for reference in case we want to restore or migrate data.
 */

function KPIsTab_OLD({ formData, editing, handleFieldChange }) {
  return (
    <div className="tab-panel">
      <h2>Key Performance Indicators</h2>
      <div className="kpi-grid">
        <div className="kpi-card">
          <h3>Loans Processed</h3>
          <div className="kpi-value">{formData.loans_processed || 0}</div>
          <div className="kpi-period">This Month</div>
        </div>
        <div className="kpi-card">
          <h3>Average Close Time</h3>
          <div className="kpi-value">{formData.avg_close_time || 0} days</div>
          <div className="kpi-period">Last 30 Days</div>
        </div>
        <div className="kpi-card">
          <h3>Customer Satisfaction</h3>
          <div className="kpi-value">{formData.satisfaction_score || 0}%</div>
          <div className="kpi-period">Overall</div>
        </div>
        <div className="kpi-card">
          <h3>Volume</h3>
          <div className="kpi-value">${(formData.volume || 0).toLocaleString()}</div>
          <div className="kpi-period">This Quarter</div>
        </div>
      </div>

      <div className="kpi-details">
        <h3>Monthly Performance</h3>
        <div className="info-grid">
          <div className="info-field">
            <label>Loans Processed</label>
            <input
              type="number"
              value={formData.loans_processed || ''}
              onChange={(e) => handleFieldChange('loans_processed', e.target.value)}
              disabled={!editing}
            />
          </div>
          <div className="info-field">
            <label>Average Close Time (days)</label>
            <input
              type="number"
              value={formData.avg_close_time || ''}
              onChange={(e) => handleFieldChange('avg_close_time', e.target.value)}
              disabled={!editing}
            />
          </div>
          <div className="info-field">
            <label>Satisfaction Score (%)</label>
            <input
              type="number"
              value={formData.satisfaction_score || ''}
              onChange={(e) => handleFieldChange('satisfaction_score', e.target.value)}
              disabled={!editing}
              min="0"
              max="100"
            />
          </div>
          <div className="info-field">
            <label>Volume ($)</label>
            <input
              type="number"
              value={formData.volume || ''}
              onChange={(e) => handleFieldChange('volume', e.target.value)}
              disabled={!editing}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default KPIsTab_OLD;
