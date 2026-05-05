import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './YearOverYear.css';
import { getToken } from '../utils/tokenStore';

function YearOverYear() {
  const navigate = useNavigate();
  const [yearlyData, setYearlyData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadYearlyData();
  }, []);

  const loadYearlyData = async () => {
    try {
      setLoading(true);
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_URL = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || '');
      const token = getToken();

      const response = await fetch(`${API_URL}/api/v1/portfolio/yearly-stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setYearlyData(Array.isArray(data) ? data : []);
      } else {
        setYearlyData([]);
      }
    } catch (error) {
      console.error('Failed to load yearly data:', error);
      setYearlyData([]);
    } finally {
      setLoading(false);
    }
  };

  const calculateROI = (current, previous) => {
    if (!previous || previous === 0) return 0;
    return ((current - previous) / previous * 100);
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const getMaxValue = (key) => {
    if (!yearlyData || yearlyData.length === 0) return 0;
    return Math.max(...yearlyData.map(d => d[key] || 0));
  };

  const getBarHeight = (value, key) => {
    const max = getMaxValue(key);
    return max > 0 ? (value / max) * 100 : 0;
  };

  if (loading) {
    return (
      <div className="year-over-year-page">
        <div className="loading">Loading yearly data...</div>
      </div>
    );
  }

  return (
    <div className="year-over-year-page">
      <div className="page-header">
        <div>
          <button className="btn-back" onClick={() => navigate('/portfolio')}>
            ← Back to Portfolio
          </button>
          <h1>Year Over Year Performance</h1>
          <p className="page-subtitle">Annual totals and ROI trends</p>
        </div>
      </div>

      {yearlyData.length === 0 && (
        <div className="placeholder-banner" style={{
          background: '#fef3c7',
          border: '1px solid #f59e0b',
          borderRadius: '8px',
          padding: '24px',
          marginBottom: '24px',
          textAlign: 'center',
          color: '#92400e'
        }}>
          <strong>No historical data available.</strong> Historical data visualization requires production data. Connect your pipeline to see real year-over-year metrics.
        </div>
      )}

      {/* ROI Summary Cards */}
      <div className="roi-cards">
        <div className="roi-card">
          <div className="roi-label">Volume Growth</div>
          <div className="roi-value">
            {yearlyData.length >= 2 ? (
              <>
                {calculateROI(
                  yearlyData[yearlyData.length - 1]?.total_volume,
                  yearlyData[yearlyData.length - 2]?.total_volume
                ).toFixed(1)}%
              </>
            ) : 'N/A'}
          </div>
          <div className="roi-subtitle">Year over Year</div>
        </div>

        <div className="roi-card">
          <div className="roi-label">Loan Count Growth</div>
          <div className="roi-value">
            {yearlyData.length >= 2 ? (
              <>
                {calculateROI(
                  yearlyData[yearlyData.length - 1]?.total_loans,
                  yearlyData[yearlyData.length - 2]?.total_loans
                ).toFixed(1)}%
              </>
            ) : 'N/A'}
          </div>
          <div className="roi-subtitle">Year over Year</div>
        </div>

        <div className="roi-card">
          <div className="roi-label">Commission Growth</div>
          <div className="roi-value">
            {yearlyData.length >= 2 ? (
              <>
                {calculateROI(
                  yearlyData[yearlyData.length - 1]?.commission_earned,
                  yearlyData[yearlyData.length - 2]?.commission_earned
                ).toFixed(1)}%
              </>
            ) : 'N/A'}
          </div>
          <div className="roi-subtitle">Year over Year</div>
        </div>

        <div className="roi-card highlight">
          <div className="roi-label">Average ROI</div>
          <div className="roi-value">
            {yearlyData.length >= 2 ? (
              <>
                {(
                  (calculateROI(
                    yearlyData[yearlyData.length - 1]?.total_volume,
                    yearlyData[yearlyData.length - 2]?.total_volume
                  ) +
                  calculateROI(
                    yearlyData[yearlyData.length - 1]?.commission_earned,
                    yearlyData[yearlyData.length - 2]?.commission_earned
                  )) / 2
                ).toFixed(1)}%
              </>
            ) : 'N/A'}
          </div>
          <div className="roi-subtitle">Composite Growth Rate</div>
        </div>
      </div>

      {/* Volume Chart */}
      <div className="chart-section">
        <h2>Total Volume by Year</h2>
        <div className="bar-chart">
          {yearlyData.map((data) => (
            <div key={data.year} className="bar-group">
              <div className="bar-container">
                <div
                  className={`bar ${data.is_current ? 'current-year' : ''}`}
                  style={{ height: `${getBarHeight(data.total_volume, 'total_volume')}%` }}
                >
                  <span className="bar-value">{formatCurrency(data.total_volume)}</span>
                </div>
              </div>
              <div className="bar-label">{data.year}{data.is_current ? ' (Current)' : ''}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Loan Count Chart */}
      <div className="chart-section">
        <h2>Total Loans by Year</h2>
        <div className="bar-chart">
          {yearlyData.map((data) => (
            <div key={data.year} className="bar-group">
              <div className="bar-container">
                <div
                  className={`bar ${data.is_current ? 'current-year' : ''}`}
                  style={{ height: `${getBarHeight(data.total_loans, 'total_loans')}%` }}
                >
                  <span className="bar-value">{data.total_loans}</span>
                </div>
              </div>
              <div className="bar-label">{data.year}{data.is_current ? ' (Current)' : ''}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Commission Chart */}
      <div className="chart-section">
        <h2>Commission Earned by Year</h2>
        <div className="bar-chart">
          {yearlyData.map((data) => (
            <div key={data.year} className="bar-group">
              <div className="bar-container">
                <div
                  className={`bar ${data.is_current ? 'current-year' : ''}`}
                  style={{ height: `${getBarHeight(data.commission_earned, 'commission_earned')}%` }}
                >
                  <span className="bar-value">{formatCurrency(data.commission_earned)}</span>
                </div>
              </div>
              <div className="bar-label">{data.year}{data.is_current ? ' (Current)' : ''}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Data Table */}
      <div className="data-table-section">
        <h2>Yearly Summary</h2>
        <div className="table-container">
          <table className="yearly-table">
            <thead>
              <tr>
                <th>Year</th>
                <th>Total Loans</th>
                <th>Total Volume</th>
                <th>Commission Earned</th>
                <th>Active Loans (EOY)</th>
                <th>Volume Growth</th>
                <th>Commission Growth</th>
              </tr>
            </thead>
            <tbody>
              {yearlyData.map((data, index) => {
                const prevData = index > 0 ? yearlyData[index - 1] : null;
                const volumeGrowth = prevData ? calculateROI(data.total_volume, prevData.total_volume) : null;
                const commissionGrowth = prevData ? calculateROI(data.commission_earned, prevData.commission_earned) : null;

                return (
                  <tr key={data.year} className={data.is_current ? 'current-year-row' : ''}>
                    <td className="year-cell">
                      {data.year}
                      {data.is_current && <span className="current-badge">Current</span>}
                    </td>
                    <td>{data.total_loans}</td>
                    <td>{formatCurrency(data.total_volume)}</td>
                    <td>{formatCurrency(data.commission_earned)}</td>
                    <td>{data.active_loans}</td>
                    <td className={volumeGrowth > 0 ? 'positive' : volumeGrowth < 0 ? 'negative' : ''}>
                      {volumeGrowth !== null ? `${volumeGrowth > 0 ? '+' : ''}${volumeGrowth.toFixed(1)}%` : 'N/A'}
                    </td>
                    <td className={commissionGrowth > 0 ? 'positive' : commissionGrowth < 0 ? 'negative' : ''}>
                      {commissionGrowth !== null ? `${commissionGrowth > 0 ? '+' : ''}${commissionGrowth.toFixed(1)}%` : 'N/A'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Year-End Note */}
      <div className="info-note">
        <strong>Note:</strong> Yearly totals are automatically captured at midnight on December 31st.
        At year-end, active loans and commission values reset for the new year, while total loans and total volume continue to accumulate across all years.
      </div>
    </div>
  );
}

export default YearOverYear;
