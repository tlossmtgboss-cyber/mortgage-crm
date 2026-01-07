import React, { useState, useEffect, useMemo } from 'react';
import './ProductionPredictor.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Trend icons and colors
const TREND_CONFIG = {
  up: { icon: '📈', color: '#10b981', label: 'Trending Up' },
  down: { icon: '📉', color: '#ef4444', label: 'Trending Down' },
  stable: { icon: '➡️', color: '#6b7280', label: 'Stable' },
};

const RISK_CONFIG = {
  ahead: { color: '#10b981', label: 'Ahead of Goal', icon: '🎯' },
  on_track: { color: '#3b82f6', label: 'On Track', icon: '✓' },
  at_risk: { color: '#f59e0b', label: 'At Risk', icon: '⚠️' },
  behind: { color: '#ef4444', label: 'Behind', icon: '🚨' },
};

const CONFIDENCE_CONFIG = {
  high: { color: '#10b981', label: 'High Confidence' },
  medium: { color: '#f59e0b', label: 'Medium Confidence' },
  low: { color: '#ef4444', label: 'Low Confidence' },
};

// Format currency
const formatCurrency = (amount) => {
  if (amount >= 1000000) {
    return `$${(amount / 1000000).toFixed(1)}M`;
  }
  if (amount >= 1000) {
    return `$${(amount / 1000).toFixed(0)}K`;
  }
  return `$${amount.toFixed(0)}`;
};

// Production Predictor Dashboard
export function ProductionPredictorDashboard({ entityId, entityType = 'lo' }) {
  const [summary, setSummary] = useState(null);
  const [goalAttainment, setGoalAttainment] = useState(null);
  const [conversions, setConversions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('forecast');

  useEffect(() => {
    fetchData();
  }, [entityId, entityType]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all data in parallel
      const [summaryRes, goalRes, conversionRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/production-predictor/summary/${entityId}?entity_type=${entityType}`),
        fetch(`${API_BASE}/api/v1/production-predictor/goal-attainment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entity_id: entityId,
            goal_units: 10,
            goal_volume: 4000000,
            goal_period_start: new Date().toISOString().split('T')[0].slice(0, 7) + '-01',
            goal_period_end: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).toISOString().split('T')[0],
          }),
        }),
        fetch(`${API_BASE}/api/v1/production-predictor/conversions/${entityId}?days=90`),
      ]);

      if (summaryRes.ok) {
        const data = await summaryRes.json();
        setSummary(data);
      }

      if (goalRes.ok) {
        const data = await goalRes.json();
        setGoalAttainment(data);
      }

      if (conversionRes.ok) {
        const data = await conversionRes.json();
        setConversions(data);
      }
    } catch (err) {
      console.error('Error fetching production data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="production-predictor loading">
        <div className="loading-spinner"></div>
        <p>Analyzing production data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="production-predictor error">
        <p>Error loading production data: {error}</p>
        <button onClick={fetchData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="production-predictor">
      <div className="predictor-header">
        <h1>Production Predictor</h1>
        <p>AI-powered forecasting and performance analysis</p>
        <div className="tab-switcher">
          <button
            className={activeTab === 'forecast' ? 'active' : ''}
            onClick={() => setActiveTab('forecast')}
          >
            Forecasts
          </button>
          <button
            className={activeTab === 'goals' ? 'active' : ''}
            onClick={() => setActiveTab('goals')}
          >
            Goals
          </button>
          <button
            className={activeTab === 'conversions' ? 'active' : ''}
            onClick={() => setActiveTab('conversions')}
          >
            Conversions
          </button>
        </div>
      </div>

      {activeTab === 'forecast' && summary && (
        <ForecastView summary={summary} />
      )}

      {activeTab === 'goals' && goalAttainment && (
        <GoalView attainment={goalAttainment} />
      )}

      {activeTab === 'conversions' && conversions && (
        <ConversionView conversions={conversions} />
      )}
    </div>
  );
}

// Forecast View Component
function ForecastView({ summary }) {
  const trend = summary.trend || {};
  const forecasts = summary.forecasts || {};
  const trendConfig = TREND_CONFIG[trend.direction] || TREND_CONFIG.stable;

  return (
    <div className="forecast-view">
      {/* Current Month */}
      <div className="section current-month-section">
        <h2>Current Month</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">MTD Units</div>
            <div className="stat-value">{summary.current_month?.mtd_units || 0}</div>
            <div className="stat-subtext">
              Projected: {summary.current_month?.projected_units || 0}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">MTD Volume</div>
            <div className="stat-value">
              {formatCurrency(summary.current_month?.mtd_volume || 0)}
            </div>
            <div className="stat-subtext">
              Projected: {formatCurrency(summary.current_month?.projected_volume || 0)}
            </div>
          </div>
          <div className="stat-card trend-card">
            <div className="stat-label">Trend</div>
            <div className="stat-value" style={{ color: trendConfig.color }}>
              {trendConfig.icon} {trend.change_pct > 0 ? '+' : ''}{trend.change_pct}%
            </div>
            <div className="stat-subtext">{trendConfig.label}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Volatility</div>
            <div className="stat-value">
              {trend.volatility?.toFixed(1) || 0}%
            </div>
            <div className="stat-subtext">
              {trend.volatility < 20 ? 'Low' : trend.volatility < 40 ? 'Medium' : 'High'}
            </div>
          </div>
        </div>
      </div>

      {/* Forecasts */}
      <div className="section forecasts-section">
        <h2>Production Forecasts</h2>
        <div className="forecasts-grid">
          {['30_day', '60_day', '90_day'].map((period) => {
            const forecast = forecasts[period];
            if (!forecast) return null;

            const confidenceConfig = CONFIDENCE_CONFIG[forecast.confidence] || CONFIDENCE_CONFIG.medium;
            const days = period.split('_')[0];

            return (
              <div key={period} className="forecast-card">
                <div className="forecast-header">
                  <span className="period-label">{days} Days</span>
                  <span
                    className="confidence-badge"
                    style={{ backgroundColor: confidenceConfig.color }}
                  >
                    {confidenceConfig.label}
                  </span>
                </div>
                <div className="forecast-content">
                  <div className="forecast-metric">
                    <span className="metric-label">Units</span>
                    <span className="metric-value">{forecast.units}</span>
                  </div>
                  <div className="forecast-metric">
                    <span className="metric-label">Volume</span>
                    <span className="metric-value">{formatCurrency(forecast.volume)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Historical Performance */}
      <div className="section historical-section">
        <h2>Historical Performance</h2>
        <div className="historical-stats">
          <div className="historical-stat">
            <span className="label">Avg Monthly Units</span>
            <span className="value">{summary.historical?.avg_monthly_units?.toFixed(1) || 0}</span>
          </div>
          <div className="historical-stat">
            <span className="label">Avg Monthly Volume</span>
            <span className="value">{formatCurrency(summary.historical?.avg_monthly_volume || 0)}</span>
          </div>
          <div className="historical-stat">
            <span className="label">Peak Month</span>
            <span className="value">{summary.historical?.peak_month || 'N/A'}</span>
          </div>
          <div className="historical-stat">
            <span className="label">Slowest Month</span>
            <span className="value">{summary.historical?.trough_month || 'N/A'}</span>
          </div>
        </div>
      </div>

      {/* Seasonality */}
      {summary.seasonality && Object.keys(summary.seasonality).length > 0 && (
        <div className="section seasonality-section">
          <h2>Seasonality Pattern</h2>
          <div className="seasonality-chart">
            {Object.entries(summary.seasonality).map(([month, factor]) => (
              <div key={month} className="seasonality-bar-wrapper">
                <div
                  className="seasonality-bar"
                  style={{
                    height: `${factor * 50}px`,
                    backgroundColor: factor > 1 ? '#10b981' : '#ef4444',
                  }}
                ></div>
                <span className="month-label">{month.slice(0, 3)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Goal View Component
function GoalView({ attainment }) {
  const riskConfig = RISK_CONFIG[attainment.risk_level] || RISK_CONFIG.on_track;

  return (
    <div className="goal-view">
      {/* Goal Progress */}
      <div className="section goal-progress-section">
        <h2>Goal Attainment</h2>
        <div className="risk-banner" style={{ backgroundColor: riskConfig.color }}>
          <span className="risk-icon">{riskConfig.icon}</span>
          <span className="risk-label">{riskConfig.label}</span>
          <span className="days-remaining">{attainment.days_remaining} days remaining</span>
        </div>

        <div className="progress-grid">
          <div className="progress-card">
            <h3>Units Progress</h3>
            <div className="progress-bar-container">
              <div
                className="progress-bar"
                style={{
                  width: `${Math.min(100, attainment.units_progress_pct)}%`,
                  backgroundColor: attainment.units_progress_pct >= attainment.units_on_track_pct ? '#10b981' : '#f59e0b',
                }}
              ></div>
              <div
                className="goal-marker"
                style={{ left: '100%' }}
              ></div>
            </div>
            <div className="progress-stats">
              <span>
                {attainment.current_units} / {attainment.goal_units} units
              </span>
              <span className="on-track">
                {attainment.units_on_track_pct}% likely to hit goal
              </span>
            </div>
            <div className="predicted-final">
              Predicted: {attainment.predicted_final_units} units
            </div>
          </div>

          <div className="progress-card">
            <h3>Volume Progress</h3>
            <div className="progress-bar-container">
              <div
                className="progress-bar"
                style={{
                  width: `${Math.min(100, attainment.volume_progress_pct)}%`,
                  backgroundColor: attainment.volume_progress_pct >= attainment.volume_on_track_pct ? '#10b981' : '#f59e0b',
                }}
              ></div>
            </div>
            <div className="progress-stats">
              <span>
                {formatCurrency(attainment.current_volume)} / {formatCurrency(attainment.goal_volume)}
              </span>
              <span className="on-track">
                {attainment.volume_on_track_pct}% likely to hit goal
              </span>
            </div>
            <div className="predicted-final">
              Predicted: {formatCurrency(attainment.predicted_final_volume)}
            </div>
          </div>
        </div>
      </div>

      {/* Required Pace */}
      <div className="section pace-section">
        <h2>Required Pace</h2>
        <div className="pace-grid">
          <div className="pace-card">
            <div className="pace-value">{attainment.units_per_day_needed.toFixed(2)}</div>
            <div className="pace-label">units per day needed</div>
          </div>
          <div className="pace-card">
            <div className="pace-value">{formatCurrency(attainment.volume_per_day_needed)}</div>
            <div className="pace-label">volume per day needed</div>
          </div>
        </div>
      </div>

      {/* Recommendations */}
      {attainment.recommendations && attainment.recommendations.length > 0 && (
        <div className="section recommendations-section">
          <h2>Recommendations</h2>
          <ul className="recommendations-list">
            {attainment.recommendations.map((rec, idx) => (
              <li key={idx}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Conversion View Component
function ConversionView({ conversions }) {
  const stages = conversions.stage_conversions || {};
  const weakSpots = conversions.weak_spots || [];

  return (
    <div className="conversion-view">
      {/* Overall Conversion */}
      <div className="section overall-section">
        <h2>Pipeline Conversion</h2>
        <div className="overall-stats">
          <div className="overall-stat">
            <div className="stat-value">
              {conversions.overall_conversion}%
            </div>
            <div className="stat-label">Overall Pull-Through</div>
            <div
              className="benchmark-indicator"
              style={{
                color: conversions.overall_conversion >= conversions.overall_benchmark ? '#10b981' : '#ef4444',
              }}
            >
              Benchmark: {conversions.overall_benchmark}%
            </div>
          </div>
        </div>
      </div>

      {/* Conversion Funnel */}
      <div className="section funnel-section">
        <h2>Conversion Funnel</h2>
        <div className="funnel">
          {Object.entries(stages).map(([stage, data], idx) => {
            const stageLabel = stage.replace(/_/g, ' → ');
            const isWeakSpot = data.rate < data.benchmark;
            const widthPct = 100 - idx * 15;

            return (
              <div
                key={stage}
                className={`funnel-stage ${isWeakSpot ? 'weak' : ''}`}
                style={{ width: `${widthPct}%` }}
              >
                <div className="stage-header">
                  <span className="stage-name">{stageLabel}</span>
                  <span className="stage-rate">
                    {(data.rate * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="stage-bar">
                  <div
                    className="stage-fill"
                    style={{
                      width: `${data.rate * 100}%`,
                      backgroundColor: isWeakSpot ? '#ef4444' : '#3b82f6',
                    }}
                  ></div>
                </div>
                <div className="stage-details">
                  <span>{data.converted || 0} / {data.total || data.total_leads || 0}</span>
                  <span className="benchmark">Target: {(data.benchmark * 100).toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Weak Spots */}
      {weakSpots.length > 0 && (
        <div className="section weak-spots-section">
          <h2>Areas for Improvement</h2>
          <div className="weak-spots-list">
            {weakSpots.map((spot, idx) => (
              <div key={idx} className="weak-spot-card">
                <div className="weak-spot-header">
                  <span className="stage">{spot.stage.replace(/_/g, ' → ')}</span>
                  <span className="gap">-{spot.gap_pct}% below benchmark</span>
                </div>
                <div className="potential">
                  Fixing this could yield +{spot.potential_units} units
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {conversions.recommendations && conversions.recommendations.length > 0 && (
        <div className="section recommendations-section">
          <h2>Recommendations</h2>
          <ul className="recommendations-list">
            {conversions.recommendations.map((rec, idx) => (
              <li key={idx}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Compact Widget for Dashboard embedding
export function ProductionPredictorWidget({ entityId, compact = false }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSummary();
  }, [entityId]);

  const fetchSummary = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/production-predictor/summary/${entityId}?entity_type=lo`
      );
      if (res.ok) {
        const data = await res.json();
        setSummary(data);
      }
    } catch (err) {
      console.error('Error fetching summary:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="predictor-widget loading">
        <div className="loading-spinner small"></div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="predictor-widget empty">
        <p>No production data available</p>
      </div>
    );
  }

  const trend = summary.trend || {};
  const trendConfig = TREND_CONFIG[trend.direction] || TREND_CONFIG.stable;
  const forecast30 = summary.forecasts?.['30_day'] || {};

  if (compact) {
    return (
      <div className="predictor-widget compact">
        <div className="widget-header">
          <span className="widget-title">Production Forecast</span>
          <span className="trend-badge" style={{ color: trendConfig.color }}>
            {trendConfig.icon} {trend.change_pct > 0 ? '+' : ''}{trend.change_pct}%
          </span>
        </div>
        <div className="widget-stats">
          <div className="widget-stat">
            <span className="value">{forecast30.units || 0}</span>
            <span className="label">30-Day Units</span>
          </div>
          <div className="widget-stat">
            <span className="value">{formatCurrency(forecast30.volume || 0)}</span>
            <span className="label">30-Day Volume</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="predictor-widget">
      <div className="widget-header">
        <h3>Production Predictor</h3>
        <span className="trend-indicator" style={{ color: trendConfig.color }}>
          {trendConfig.icon} {trendConfig.label}
        </span>
      </div>

      <div className="widget-content">
        <div className="current-production">
          <div className="production-stat">
            <span className="label">MTD</span>
            <span className="value">{summary.current_month?.mtd_units || 0} units</span>
          </div>
          <div className="production-stat">
            <span className="label">Projected</span>
            <span className="value">{summary.current_month?.projected_units || 0} units</span>
          </div>
        </div>

        <div className="forecasts-row">
          {['30_day', '60_day', '90_day'].map((period) => {
            const forecast = summary.forecasts?.[period];
            if (!forecast) return null;
            const days = period.split('_')[0];

            return (
              <div key={period} className="mini-forecast">
                <span className="days">{days}d</span>
                <span className="units">{forecast.units}</span>
                <span className="volume">{formatCurrency(forecast.volume)}</span>
              </div>
            );
          })}
        </div>
      </div>

      <a href="/production-predictor" className="widget-link">
        View Full Analysis →
      </a>
    </div>
  );
}

// Page wrapper component
export function ProductionPredictorPage() {
  // Get current user ID from auth context (simplified for now)
  const entityId = 'current-user';

  return (
    <div className="production-predictor-page">
      <ProductionPredictorDashboard entityId={entityId} entityType="lo" />
    </div>
  );
}

export default ProductionPredictorDashboard;
