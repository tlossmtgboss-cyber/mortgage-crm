import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import './ProductionPredictorDetail.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Format currency
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

// Format date
const formatDate = (dateStr) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

// View configurations
const VIEW_CONFIG = {
  mtd_units: {
    title: 'Month-to-Date Units',
    subtitle: 'Loans closed this month',
    filter: { status: 'funded', period: 'mtd' },
  },
  mtd_volume: {
    title: 'Month-to-Date Volume',
    subtitle: 'Total funded volume this month',
    filter: { status: 'funded', period: 'mtd' },
  },
  projected_units: {
    title: 'Projected Units',
    subtitle: 'Loans expected to close this month',
    filter: { status: 'in_pipeline', period: 'projected' },
  },
  projected_volume: {
    title: 'Projected Volume',
    subtitle: 'Expected volume to close this month',
    filter: { status: 'in_pipeline', period: 'projected' },
  },
  forecast_30: {
    title: '30-Day Forecast',
    subtitle: 'Loans expected to close in next 30 days',
    filter: { status: 'in_pipeline', period: '30_day' },
  },
  forecast_60: {
    title: '60-Day Forecast',
    subtitle: 'Loans expected to close in next 60 days',
    filter: { status: 'in_pipeline', period: '60_day' },
  },
  forecast_90: {
    title: '90-Day Forecast',
    subtitle: 'Loans expected to close in next 90 days',
    filter: { status: 'in_pipeline', period: '90_day' },
  },
  trend: {
    title: 'Production Trend Analysis',
    subtitle: 'Month-over-month production comparison',
    filter: { view: 'trend' },
  },
  historical: {
    title: 'Historical Performance',
    subtitle: 'Past production data',
    filter: { view: 'historical' },
  },
};

export default function ProductionPredictorDetail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const view = searchParams.get('view') || 'mtd_units';
  const period = searchParams.get('period');

  const [loans, setLoans] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const viewConfig = VIEW_CONFIG[view] || VIEW_CONFIG.mtd_units;

  useEffect(() => {
    fetchData();
  }, [view, period]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      // Determine the API call based on view type
      let loansData = [];
      let summaryData = null;

      if (view === 'trend' || view === 'historical') {
        // Fetch trend/historical data
        const res = await fetch(
          `${API_BASE}/api/v1/production-predictor/summary/current-user?entity_type=lo`,
          { headers }
        );
        if (res.ok) {
          summaryData = await res.json();
        }
      } else {
        // Build query params for loan list
        const params = new URLSearchParams();

        // Set status filter
        if (view.includes('mtd')) {
          params.append('status', 'funded');
          // Get current month date range
          const now = new Date();
          const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
          params.append('funded_after', startOfMonth.toISOString().split('T')[0]);
        } else if (view.includes('forecast') || view.includes('projected')) {
          // Pipeline loans
          params.append('status__in', 'processing,submitted,underwriting,approved,clear_to_close');

          // Set expected close date range
          const now = new Date();
          let daysAhead = 30;
          if (view === 'forecast_60' || period === '60_day') daysAhead = 60;
          if (view === 'forecast_90' || period === '90_day') daysAhead = 90;

          const endDate = new Date(now.getTime() + daysAhead * 24 * 60 * 60 * 1000);
          params.append('expected_close_before', endDate.toISOString().split('T')[0]);
        }

        // Fetch loans
        const res = await fetch(
          `${API_BASE}/api/v1/loans/?${params.toString()}`,
          { headers }
        );

        if (res.ok) {
          const data = await res.json();
          loansData = Array.isArray(data) ? data : (data.items || data.loans || []);
        }

        // Calculate summary
        summaryData = {
          total_count: loansData.length,
          total_volume: loansData.reduce((sum, loan) => sum + (loan.loan_amount || 0), 0),
          avg_loan_amount: loansData.length > 0
            ? loansData.reduce((sum, loan) => sum + (loan.loan_amount || 0), 0) / loansData.length
            : 0,
        };
      }

      setLoans(loansData);
      setSummary(summaryData);
    } catch (err) {
      console.error('Error fetching detail data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLoanClick = (loanId) => {
    navigate(`/loans/${loanId}`);
  };

  const handleBack = () => {
    navigate('/production-predictor');
  };

  if (loading) {
    return (
      <div className="pp-detail-page">
        <div className="pp-detail-loading">
          <div className="loading-spinner"></div>
          <p>Loading data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pp-detail-page">
        <div className="pp-detail-error">
          <h2>Error Loading Data</h2>
          <p>{error}</p>
          <button onClick={fetchData}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="pp-detail-page">
      {/* Header */}
      <div className="pp-detail-header">
        <button className="back-button" onClick={handleBack}>
          ← Back to Production Predictor
        </button>
        <div className="header-content">
          <h1>{viewConfig.title}</h1>
          <p>{viewConfig.subtitle}</p>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="pp-detail-summary">
          <div className="summary-card">
            <span className="summary-value">{summary.total_count || loans.length}</span>
            <span className="summary-label">Total Loans</span>
          </div>
          <div className="summary-card">
            <span className="summary-value">{formatCurrency(summary.total_volume)}</span>
            <span className="summary-label">Total Volume</span>
          </div>
          <div className="summary-card">
            <span className="summary-value">{formatCurrency(summary.avg_loan_amount)}</span>
            <span className="summary-label">Average Loan</span>
          </div>
        </div>
      )}

      {/* Trend/Historical View */}
      {(view === 'trend' || view === 'historical') && summary && (
        <div className="pp-detail-trends">
          {summary.historical && (
            <div className="trend-section">
              <h3>Historical Performance</h3>
              <div className="trend-stats">
                <div className="trend-stat">
                  <span className="label">Avg Monthly Units</span>
                  <span className="value">{summary.historical.avg_monthly_units?.toFixed(1) || 0}</span>
                </div>
                <div className="trend-stat">
                  <span className="label">Avg Monthly Volume</span>
                  <span className="value">{formatCurrency(summary.historical.avg_monthly_volume)}</span>
                </div>
                <div className="trend-stat">
                  <span className="label">Peak Month</span>
                  <span className="value">{summary.historical.peak_month || 'N/A'}</span>
                </div>
                <div className="trend-stat">
                  <span className="label">Slowest Month</span>
                  <span className="value">{summary.historical.trough_month || 'N/A'}</span>
                </div>
              </div>
            </div>
          )}

          {summary.trend && (
            <div className="trend-section">
              <h3>Current Trend</h3>
              <div className="trend-indicator">
                <span className={`trend-badge ${summary.trend.direction}`}>
                  {summary.trend.direction === 'up' ? '📈' : summary.trend.direction === 'down' ? '📉' : '➡️'}
                  {summary.trend.change_pct > 0 ? '+' : ''}{summary.trend.change_pct}%
                </span>
                <span className="trend-label">
                  {summary.trend.direction === 'up' ? 'Trending Up' :
                   summary.trend.direction === 'down' ? 'Trending Down' : 'Stable'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loans Table */}
      {loans.length > 0 && (
        <div className="pp-detail-table-container">
          <h3>Loan Details ({loans.length} loans)</h3>
          <table className="pp-detail-table">
            <thead>
              <tr>
                <th>Loan #</th>
                <th>Borrower</th>
                <th>Property Address</th>
                <th>Loan Amount</th>
                <th>Status</th>
                <th>Expected Close</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr key={loan.id} onClick={() => handleLoanClick(loan.id)}>
                  <td className="loan-number">{loan.loan_number || loan.id?.slice(0, 8)}</td>
                  <td>{loan.borrower_name || loan.borrower_first_name || '-'}</td>
                  <td className="address">{loan.property_address || loan.property_street || '-'}</td>
                  <td className="amount">{formatCurrency(loan.loan_amount)}</td>
                  <td>
                    <span className={`status-badge ${loan.status?.toLowerCase()}`}>
                      {loan.status?.replace(/_/g, ' ') || '-'}
                    </span>
                  </td>
                  <td>{formatDate(loan.expected_close_date || loan.estimated_closing_date)}</td>
                  <td>
                    <button
                      className="view-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleLoanClick(loan.id);
                      }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty State */}
      {loans.length === 0 && !view.includes('trend') && !view.includes('historical') && (
        <div className="pp-detail-empty">
          <div className="empty-icon">📊</div>
          <h3>No Loans Found</h3>
          <p>There are no loans matching the selected criteria.</p>
        </div>
      )}
    </div>
  );
}
