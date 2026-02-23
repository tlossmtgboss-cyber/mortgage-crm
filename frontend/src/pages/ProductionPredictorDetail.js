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

// Stage display name mapping
const STAGE_DISPLAY = {
  APPLICATION: 'Application',
  DISCLOSED: 'Disclosed',
  PROCESSING: 'Processing',
  SUBMITTED: 'Submitted',
  UNDERWRITING: 'Underwriting',
  UW_RECEIVED: 'UW Received',
  CONDITIONAL_APPROVAL: 'Conditional',
  APPROVED: 'Approved',
  SUSPENDED: 'Suspended',
  CTC: 'Clear to Close',
  CLEAR_TO_CLOSE: 'Clear to Close',
  CLOSING: 'Closing',
  DOCS: 'Docs',
  DOCS_OUT: 'Docs Out',
  FUNDED: 'Funded',
};

// View configurations
const VIEW_CONFIG = {
  mtd_units: {
    title: 'Month-to-Date Units',
    subtitle: 'Loans funded this month',
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
    subtitle: 'Loans expected to close in the next 30 days',
    filter: { status: 'in_pipeline', period: '30_day' },
  },
  forecast_60: {
    title: '60-Day Forecast',
    subtitle: 'Loans expected to close in the next 60 days',
    filter: { status: 'in_pipeline', period: '60_day' },
  },
  forecast_90: {
    title: '90-Day Forecast',
    subtitle: 'Loans expected to close in the next 90 days',
    filter: { status: 'in_pipeline', period: '90_day' },
  },
  trend: {
    title: 'Production Trend Analysis',
    subtitle: 'Month-over-month production comparison',
    filter: { view: 'trend' },
  },
  historical: {
    title: 'Historical Performance',
    subtitle: 'Past production data and patterns',
    filter: { view: 'historical' },
  },
  goal_units: {
    title: 'Goal Progress — Units',
    subtitle: 'Pipeline loans contributing to your unit goal',
    filter: { status: 'in_pipeline', period: 'goal' },
  },
  goal_volume: {
    title: 'Goal Progress — Volume',
    subtitle: 'Pipeline loans contributing to your volume goal',
    filter: { status: 'in_pipeline', period: 'goal' },
  },
  pace_units: {
    title: 'Required Pace — Units',
    subtitle: 'Active pipeline loans needed to hit your pace target',
    filter: { status: 'in_pipeline', period: 'goal' },
  },
  pace_volume: {
    title: 'Required Pace — Volume',
    subtitle: 'Active pipeline loans by volume toward your pace target',
    filter: { status: 'in_pipeline', period: 'goal' },
  },
  conversion_overall: {
    title: 'Overall Pipeline Conversion',
    subtitle: 'All active pipeline loans across conversion stages',
    filter: { status: 'in_pipeline', period: 'all' },
  },
};

// Generate a view config for dynamic conversion stages
const getViewConfig = (view) => {
  if (VIEW_CONFIG[view]) return VIEW_CONFIG[view];
  if (view?.startsWith('conversion_')) {
    const stage = view.replace('conversion_', '').replace(/_/g, ' ');
    return {
      title: `Conversion — ${stage.replace(/\b\w/g, c => c.toUpperCase())}`,
      subtitle: `Loans in the ${stage} conversion stage`,
      filter: { status: 'in_pipeline', period: 'conversion' },
    };
  }
  return VIEW_CONFIG.mtd_units;
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

  const viewConfig = getViewConfig(view);

  useEffect(() => {
    fetchData();
  }, [view, period]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      let loansData = [];
      let summaryData = null;

      if (view === 'trend' || view === 'historical') {
        // Fetch trend/historical data from summary endpoint
        const res = await fetch(
          `${API_BASE}/api/v1/production-predictor/summary/current-user?entity_type=lo`,
          { headers }
        );
        if (res.ok) {
          summaryData = await res.json();
        }

        // Also fetch recent funded loans for the table
        const loansRes = await fetch(
          `${API_BASE}/api/v1/loans/?limit=50`,
          { headers }
        );
        if (loansRes.ok) {
          const data = await loansRes.json();
          loansData = Array.isArray(data) ? data : (data.items || data.loans || []);
        }
      } else {
        // Build query params for loan list
        const params = new URLSearchParams();
        params.append('limit', '100');

        if (view.includes('mtd')) {
          // Funded this month
          const now = new Date();
          const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
          params.append('status', 'funded');
          params.append('funded_after', startOfMonth.toISOString().split('T')[0]);
        } else if (view.includes('forecast') || view.includes('projected')) {
          // Pipeline loans with expected close
          params.append('status__in', 'processing,submitted,underwriting,uw_received,conditional_approval,approved,clear_to_close,closing,docs,docs_out');

          const now = new Date();
          let daysAhead = 30;
          if (view === 'forecast_60' || period === '60_day') daysAhead = 60;
          if (view === 'forecast_90' || period === '90_day') daysAhead = 90;
          if (view.includes('projected')) {
            // End of current month
            daysAhead = Math.ceil((new Date(now.getFullYear(), now.getMonth() + 1, 0) - now) / (24 * 60 * 60 * 1000));
          }

          const endDate = new Date(now.getTime() + daysAhead * 24 * 60 * 60 * 1000);
          params.append('expected_close_before', endDate.toISOString().split('T')[0]);
        } else if (view.startsWith('goal_') || view.startsWith('pace_')) {
          // Active pipeline toward monthly goal — all non-terminal stages
          params.append('status__in', 'application,disclosed,processing,submitted,underwriting,uw_received,conditional_approval,approved,clear_to_close,closing,docs,docs_out');
        } else if (view.startsWith('conversion_')) {
          // Pipeline loans for conversion analysis
          params.append('status__in', 'application,disclosed,processing,submitted,underwriting,uw_received,conditional_approval,approved,clear_to_close,closing,docs,docs_out,funded');
        } else {
          // Default: all active pipeline
          params.append('status__in', 'processing,submitted,underwriting,approved,clear_to_close');
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

        // Calculate summary stats
        const totalVolume = loansData.reduce((sum, loan) => sum + (loan.loan_amount || loan.amount || 0), 0);
        summaryData = {
          total_count: loansData.length,
          total_volume: totalVolume,
          avg_loan_amount: loansData.length > 0 ? totalVolume / loansData.length : 0,
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
    navigate(`/active-loans/${loanId}`);
  };

  const handleBack = () => {
    navigate('/production-predictor');
  };

  if (loading) {
    return (
      <div className="pp-detail-page">
        <div className="pp-detail-loading">
          <div className="loading-spinner"></div>
          <p>Loading loan data...</p>
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
      {summary && !view.includes('trend') && !view.includes('historical') && (
        <div className="pp-detail-summary">
          <div className="summary-card highlight">
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
              <div className="trend-indicator-row">
                <span className={`trend-badge-lg ${summary.trend.direction}`}>
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
          <div className="table-header-row">
            <h3>Loan Details</h3>
            <span className="loan-count">{loans.length} loans</span>
          </div>
          <div className="table-scroll">
            <table className="pp-detail-table">
              <thead>
                <tr>
                  <th>Loan #</th>
                  <th>Borrower</th>
                  <th>Property Address</th>
                  <th>Loan Amount</th>
                  <th>Stage</th>
                  <th>Expected Close</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loans.map((loan) => {
                  const stage = (loan.status || loan.stage || '').toUpperCase();
                  const stageDisplay = STAGE_DISPLAY[stage] || (loan.status || loan.stage || '-').replace(/_/g, ' ');

                  return (
                    <tr key={loan.id} onClick={() => handleLoanClick(loan.id)}>
                      <td className="loan-number">{loan.loan_number || loan.id?.toString().slice(0, 8)}</td>
                      <td className="borrower-name">
                        {loan.borrower_name || loan.borrower_first_name || '-'}
                      </td>
                      <td className="address">{loan.property_address || loan.property_street || '-'}</td>
                      <td className="amount">{formatCurrency(loan.loan_amount || loan.amount)}</td>
                      <td>
                        <span className={`status-badge ${stage.toLowerCase()}`}>
                          {stageDisplay}
                        </span>
                      </td>
                      <td className="date-col">{formatDate(loan.expected_close_date || loan.estimated_closing_date || loan.closing_date)}</td>
                      <td>
                        <button
                          className="view-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleLoanClick(loan.id);
                          }}
                        >
                          View →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty State */}
      {loans.length === 0 && !view.includes('trend') && !view.includes('historical') && (
        <div className="pp-detail-empty">
          <div className="empty-icon">📊</div>
          <h3>No Loans Found</h3>
          <p>There are no loans matching the selected criteria.</p>
          <button className="back-link" onClick={handleBack}>
            ← Back to Production Predictor
          </button>
        </div>
      )}
    </div>
  );
}
