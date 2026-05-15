/**
 * HomeValueIntelligence Component
 *
 * Dedicated home value tracking dashboard for MUM (Member Until Maturity) stage.
 * Features:
 * - Real-time home value estimates
 * - Equity tracking and visualization
 * - Appreciation history charts
 * - Market comparison data
 * - AI-generated insights and opportunities
 * - Equity unlock calculator
 */

import React, { useState, useEffect, useCallback } from 'react';
import { homeValueApi } from '../../services/portalApi';
import './HomeValueIntelligence.css';

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function HomeValueIntelligence({ loanId, onRefresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeView, setActiveView] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);

  // Fetch home value data
  const fetchData = useCallback(async () => {
    if (!loanId) return;

    try {
      setLoading(true);
      const dashboard = await homeValueApi.getHomeValueDashboard(loanId);
      setData(dashboard);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch home value data:', err);
      setError(err.message || 'Failed to load home value data');
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  // Refresh insights
  const handleRefreshInsights = async () => {
    setRefreshing(true);
    try {
      await homeValueApi.generateInsights(loanId);
      await fetchData();
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Failed to refresh insights:', err);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return <HomeValueSkeleton />;
  }

  if (error) {
    return (
      <div className="hv-error-state">
        <span className="error-icon">🏠</span>
        <h3>Unable to Load Home Value Data</h3>
        <p>{error}</p>
        <button onClick={fetchData} className="retry-btn">Try Again</button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="hv-empty-state">
        <span className="empty-icon">🏠</span>
        <h3>Home Value Intelligence</h3>
        <p>Home value tracking will be available once your property baseline is set.</p>
      </div>
    );
  }

  return (
    <div className="home-value-intelligence">
      {/* Header */}
      <header className="hvi-header">
        <div className="header-content">
          <div className="header-icon">🏠</div>
          <div className="header-text">
            <h2>Home Value Intelligence</h2>
            <p>Track your home's value and equity over time</p>
          </div>
        </div>
        <button
          className="refresh-btn"
          onClick={handleRefreshInsights}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : '🔄 Refresh'}
        </button>
      </header>

      {/* View Tabs */}
      <nav className="hvi-tabs">
        <button
          className={`tab-btn ${activeView === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveView('overview')}
        >
          Overview
        </button>
        <button
          className={`tab-btn ${activeView === 'equity' ? 'active' : ''}`}
          onClick={() => setActiveView('equity')}
        >
          Equity Details
        </button>
        <button
          className={`tab-btn ${activeView === 'market' ? 'active' : ''}`}
          onClick={() => setActiveView('market')}
        >
          Market Trends
        </button>
        <button
          className={`tab-btn ${activeView === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveView('insights')}
        >
          Insights
        </button>
      </nav>

      {/* Content */}
      <div className="hvi-content">
        {activeView === 'overview' && (
          <OverviewView data={data} />
        )}
        {activeView === 'equity' && (
          <EquityView data={data} loanId={loanId} />
        )}
        {activeView === 'market' && (
          <MarketView data={data} />
        )}
        {activeView === 'insights' && (
          <InsightsView data={data} loanId={loanId} onDismiss={fetchData} />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// OVERVIEW VIEW
// =============================================================================

function OverviewView({ data }) {
  const {
    current_value,
    baseline_value,
    appreciation,
    equity,
    property_info
  } = data || {};

  const estimatedValue = current_value?.estimated_value || 0;
  const purchasePrice = baseline_value?.purchase_price || 0;
  const totalAppreciation = appreciation?.total_change || 0;
  const appreciationPercent = appreciation?.percent_change || 0;
  const totalEquity = equity?.total_equity || 0;
  const currentLtv = (equity?.current_ltv || 0) * 100;

  return (
    <div className="overview-view">
      {/* Main Value Card */}
      <div className="value-hero">
        <div className="value-main">
          <span className="value-label">Estimated Home Value</span>
          <span className="value-amount">{formatCurrency(estimatedValue)}</span>
          <div className="value-range">
            <span>Range: {formatCurrency(current_value?.value_low || 0)} - {formatCurrency(current_value?.value_high || 0)}</span>
          </div>
          <div className="value-confidence">
            <span className="confidence-label">Confidence:</span>
            <span className={`confidence-value ${current_value?.confidence || 'medium'}`}>
              {(current_value?.confidence || 'Medium').charAt(0).toUpperCase() + (current_value?.confidence || 'Medium').slice(1)}
            </span>
          </div>
        </div>

        <div className="appreciation-badge">
          <span className={`appreciation-change ${totalAppreciation >= 0 ? 'positive' : 'negative'}`}>
            {totalAppreciation >= 0 ? '↑' : '↓'} {formatCurrency(Math.abs(totalAppreciation))}
          </span>
          <span className="appreciation-percent">
            {appreciationPercent >= 0 ? '+' : ''}{appreciationPercent.toFixed(1)}%
          </span>
          <span className="appreciation-label">Since Purchase</span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-icon">💰</span>
          <span className="stat-value">{formatCurrency(purchasePrice)}</span>
          <span className="stat-label">Purchase Price</span>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📈</span>
          <span className="stat-value">{formatCurrency(totalAppreciation)}</span>
          <span className="stat-label">Total Appreciation</span>
        </div>
        <div className="stat-card highlight">
          <span className="stat-icon">🏦</span>
          <span className="stat-value">{formatCurrency(totalEquity)}</span>
          <span className="stat-label">Your Equity</span>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📊</span>
          <span className="stat-value">{currentLtv.toFixed(1)}%</span>
          <span className="stat-label">Current LTV</span>
        </div>
      </div>

      {/* Property Info */}
      {property_info && (
        <div className="property-info-card">
          <h3>Property Details</h3>
          <div className="property-details">
            {property_info.address && (
              <div className="detail-row">
                <span className="detail-label">Address</span>
                <span className="detail-value">{property_info.address}</span>
              </div>
            )}
            {property_info.bedrooms && (
              <div className="detail-row">
                <span className="detail-label">Bedrooms</span>
                <span className="detail-value">{property_info.bedrooms}</span>
              </div>
            )}
            {property_info.bathrooms && (
              <div className="detail-row">
                <span className="detail-label">Bathrooms</span>
                <span className="detail-value">{property_info.bathrooms}</span>
              </div>
            )}
            {property_info.square_feet && (
              <div className="detail-row">
                <span className="detail-label">Square Feet</span>
                <span className="detail-value">{property_info.square_feet.toLocaleString()}</span>
              </div>
            )}
            {property_info.year_built && (
              <div className="detail-row">
                <span className="detail-label">Year Built</span>
                <span className="detail-value">{property_info.year_built}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Last Updated */}
      {current_value?.last_updated && (
        <div className="last-updated">
          Last updated: {new Date(current_value.last_updated).toLocaleDateString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric'
          })}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// EQUITY VIEW
// =============================================================================

function EquityView({ data, loanId }) {
  const [equityUnlock, setEquityUnlock] = useState(null);
  const [targetLtv, setTargetLtv] = useState(80);
  const [calculating, setCalculating] = useState(false);

  const { equity, current_value } = data || {};
  const currentBalance = equity?.current_loan_balance || 0;
  const totalEquity = equity?.total_equity || 0;
  const estimatedValue = current_value?.estimated_value || 0;
  const currentLtv = (equity?.current_ltv || 0) * 100;

  // Calculate equity unlock potential
  const calculateUnlock = async () => {
    setCalculating(true);
    try {
      const result = await homeValueApi.calculateEquityUnlock(loanId, currentBalance, targetLtv / 100);
      setEquityUnlock(result);
    } catch (err) {
      console.error('Failed to calculate equity unlock:', err);
    } finally {
      setCalculating(false);
    }
  };

  useEffect(() => {
    if (loanId && currentBalance) {
      calculateUnlock();
    }
  }, [loanId, currentBalance, targetLtv]);

  return (
    <div className="equity-view">
      {/* Equity Breakdown */}
      <div className="equity-breakdown-card">
        <h3>Equity Breakdown</h3>
        <div className="breakdown-visual">
          <div className="breakdown-bar">
            <div
              className="breakdown-fill equity"
              style={{ width: `${Math.min(100 - currentLtv, 100)}%` }}
            />
            <div
              className="breakdown-fill loan"
              style={{ width: `${Math.min(currentLtv, 100)}%` }}
            />
          </div>
          <div className="breakdown-legend">
            <div className="legend-item equity">
              <span className="legend-dot" />
              <span className="legend-label">Your Equity</span>
              <span className="legend-value">{formatCurrency(totalEquity)}</span>
            </div>
            <div className="legend-item loan">
              <span className="legend-dot" />
              <span className="legend-label">Loan Balance</span>
              <span className="legend-value">{formatCurrency(currentBalance)}</span>
            </div>
          </div>
        </div>

        <div className="equity-details">
          <div className="detail-row">
            <span>Home Value</span>
            <span>{formatCurrency(estimatedValue)}</span>
          </div>
          <div className="detail-row subtract">
            <span>Loan Balance</span>
            <span>- {formatCurrency(currentBalance)}</span>
          </div>
          <div className="detail-row total">
            <span>Total Equity</span>
            <span>{formatCurrency(totalEquity)}</span>
          </div>
        </div>
      </div>

      {/* Equity Unlock Calculator */}
      <div className="equity-unlock-card">
        <h3>Equity Unlock Calculator</h3>
        <p className="calculator-desc">
          See how much equity you could access through cash-out refinancing or a HELOC.
        </p>

        <div className="ltv-selector">
          <label>Target LTV</label>
          <div className="ltv-options">
            {[80, 85, 90].map(ltv => (
              <button
                key={ltv}
                className={`ltv-btn ${targetLtv === ltv ? 'active' : ''}`}
                onClick={() => setTargetLtv(ltv)}
              >
                {ltv}%
              </button>
            ))}
          </div>
        </div>

        {calculating ? (
          <div className="calculating">Calculating...</div>
        ) : equityUnlock ? (
          <div className="unlock-results">
            <div className="result-main">
              <span className="result-label">Available to Unlock</span>
              <span className="result-value">
                {formatCurrency(equityUnlock.available_equity || 0)}
              </span>
            </div>
            <div className="result-details">
              <div className="result-row">
                <span>Max Loan at {targetLtv}% LTV</span>
                <span>{formatCurrency(equityUnlock.max_loan_amount || 0)}</span>
              </div>
              <div className="result-row">
                <span>Current Loan Balance</span>
                <span>{formatCurrency(currentBalance)}</span>
              </div>
              <div className="result-row highlight">
                <span>Cash Available</span>
                <span>{formatCurrency(equityUnlock.available_equity || 0)}</span>
              </div>
            </div>
            <button className="cta-btn">Explore Your Options</button>
          </div>
        ) : (
          <div className="no-equity">
            Unable to calculate equity unlock at this time.
          </div>
        )}
      </div>

      {/* PMI Status */}
      {currentLtv > 80 && (
        <div className="pmi-card">
          <div className="pmi-header">
            <span className="pmi-icon">📋</span>
            <h3>PMI Status</h3>
          </div>
          <p>
            Your current LTV is {currentLtv.toFixed(1)}%. Once you reach 80% LTV,
            you may be eligible to remove PMI.
          </p>
          <div className="pmi-progress">
            <div className="pmi-bar">
              <div
                className="pmi-fill"
                style={{ width: `${Math.min((100 - currentLtv) / 20 * 100, 100)}%` }}
              />
            </div>
            <span className="pmi-target">
              {formatCurrency((estimatedValue * 0.8) - currentBalance)} to go
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// MARKET VIEW
// =============================================================================

function MarketView({ data }) {
  const { market_data, appreciation } = data || {};

  // Simulated market comparison data
  const marketComps = market_data?.comparables || [];
  const neighborhoodTrend = market_data?.neighborhood_trend || 0;
  const cityTrend = market_data?.city_trend || 0;

  return (
    <div className="market-view">
      {/* Market Trends */}
      <div className="market-trends-card">
        <h3>Market Trends</h3>
        <div className="trends-grid">
          <div className="trend-item">
            <span className="trend-label">Your Home</span>
            <span className={`trend-value ${(appreciation?.percent_change || 0) >= 0 ? 'positive' : 'negative'}`}>
              {(appreciation?.percent_change || 0) >= 0 ? '+' : ''}{(appreciation?.percent_change || 0).toFixed(1)}%
            </span>
            <span className="trend-period">Since Purchase</span>
          </div>
          <div className="trend-item">
            <span className="trend-label">Neighborhood</span>
            <span className={`trend-value ${neighborhoodTrend >= 0 ? 'positive' : 'negative'}`}>
              {neighborhoodTrend >= 0 ? '+' : ''}{neighborhoodTrend.toFixed(1)}%
            </span>
            <span className="trend-period">Last 12 Months</span>
          </div>
          <div className="trend-item">
            <span className="trend-label">City Average</span>
            <span className={`trend-value ${cityTrend >= 0 ? 'positive' : 'negative'}`}>
              {cityTrend >= 0 ? '+' : ''}{cityTrend.toFixed(1)}%
            </span>
            <span className="trend-period">Last 12 Months</span>
          </div>
        </div>
      </div>

      {/* Appreciation History */}
      <div className="appreciation-history-card">
        <h3>Value History</h3>
        {appreciation?.history?.length > 0 ? (
          <div className="history-chart">
            {appreciation.history.map((point, idx) => (
              <div key={idx} className="history-point">
                <span className="history-date">
                  {new Date(point.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })}
                </span>
                <span className="history-value">{formatCurrency(point.value)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="no-history">
            Value history will be available as we track your home over time.
          </div>
        )}
      </div>

      {/* Comparable Sales */}
      {marketComps.length > 0 && (
        <div className="comparables-card">
          <h3>Recent Nearby Sales</h3>
          <div className="comps-list">
            {marketComps.map((comp, idx) => (
              <div key={idx} className="comp-item">
                <div className="comp-address">{comp.address}</div>
                <div className="comp-details">
                  <span>{comp.beds}bd / {comp.baths}ba</span>
                  <span>{comp.sqft?.toLocaleString()} sqft</span>
                </div>
                <div className="comp-sale">
                  <span className="comp-price">{formatCurrency(comp.sale_price)}</span>
                  <span className="comp-date">{comp.sale_date}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// INSIGHTS VIEW
// =============================================================================

function InsightsView({ data, loanId, onDismiss }) {
  const { insights } = data || {};

  const handleDismissInsight = async (insightId) => {
    try {
      await homeValueApi.dismissInsight(insightId);
      if (onDismiss) onDismiss();
    } catch (err) {
      console.error('Failed to dismiss insight:', err);
    }
  };

  if (!insights?.length) {
    return (
      <div className="insights-view">
        <div className="no-insights">
          <span className="insights-icon">💡</span>
          <h3>No Active Insights</h3>
          <p>We'll notify you when we identify opportunities or important updates about your home value.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="insights-view">
      <div className="insights-header">
        <h3>Personalized Insights</h3>
        <p>Opportunities and recommendations based on your home's value and market conditions.</p>
      </div>

      <div className="insights-list">
        {insights.map((insight, idx) => (
          <InsightCard
            key={insight.id || idx}
            insight={insight}
            onDismiss={() => handleDismissInsight(insight.id)}
          />
        ))}
      </div>
    </div>
  );
}

function InsightCard({ insight, onDismiss }) {
  const typeConfig = {
    opportunity: { icon: '💡', color: '#2D7A52', bg: '#d1fae5' },
    alert: { icon: '⚠️', color: '#f59e0b', bg: '#fef3c7' },
    info: { icon: 'ℹ️', color: '#3b82f6', bg: '#dbeafe' },
    action: { icon: '🎯', color: '#B8924A', bg: '#FAF3E5' },
  };

  const config = typeConfig[insight.type] || typeConfig.info;

  return (
    <div className="insight-card" style={{ borderLeftColor: config.color }}>
      <div className="insight-header">
        <span className="insight-icon" style={{ backgroundColor: config.bg }}>
          {config.icon}
        </span>
        <div className="insight-title">
          <h4>{insight.title}</h4>
          {insight.priority && (
            <span className={`priority-badge ${insight.priority}`}>
              {insight.priority}
            </span>
          )}
        </div>
        <button className="dismiss-btn" onClick={onDismiss}>×</button>
      </div>
      <p className="insight-message">{insight.message || insight.description}</p>
      {insight.potential_value && (
        <div className="insight-value">
          <span>Potential Value:</span>
          <span className="value">{formatCurrency(insight.potential_value)}</span>
        </div>
      )}
      {insight.action_label && (
        <button className="insight-action-btn">{insight.action_label}</button>
      )}
    </div>
  );
}

// =============================================================================
// SKELETON LOADER
// =============================================================================

function HomeValueSkeleton() {
  return (
    <div className="hv-skeleton">
      <div className="skeleton-header">
        <div className="skeleton-text" style={{ width: '200px', height: '24px' }} />
        <div className="skeleton-text" style={{ width: '150px', height: '16px' }} />
      </div>
      <div className="skeleton-hero">
        <div className="skeleton-block" style={{ height: '180px' }} />
      </div>
      <div className="skeleton-grid">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="skeleton-card">
            <div className="skeleton-block" style={{ height: '100px' }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function formatCurrency(amount) {
  if (amount === null || amount === undefined) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

// Export as default
export { HomeValueIntelligence };
