/**
 * CalendarAnalytics - Calendar analytics dashboard component.
 *
 * Displays:
 *   - KPI cards: Total Appointments, Completion Rate, Avg Duration, Utilization
 *   - Trend bar chart (CSS-only vertical bars)
 *   - Appointment type distribution (horizontal bar chart)
 *   - Busiest hours heatmap (7x24 grid)
 *   - LO breakdown table (admin only)
 *
 * Period selector: 7 days, 30 days, 90 days
 * No external charting libraries; all visualizations are CSS-only.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { calendarAnalyticsAPI } from '../../services/api';
import { toast } from 'react-toastify';
import '../../styles/calendar-analytics.css';

const PERIODS = [
  { key: '7d', label: '7 Days' },
  { key: '30d', label: '30 Days' },
  { key: '90d', label: '90 Days' },
];

const DAY_ABBREVS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => {
  if (i === 0) return '12a';
  if (i < 12) return `${i}a`;
  if (i === 12) return '12p';
  return `${i - 12}p`;
});

// Working hours range for heatmap display (show 6am-9pm to reduce noise)
const HEATMAP_START_HOUR = 6;
const HEATMAP_END_HOUR = 21;
const HEATMAP_HOURS = Array.from(
  { length: HEATMAP_END_HOUR - HEATMAP_START_HOUR },
  (_, i) => HEATMAP_START_HOUR + i
);

export default function CalendarAnalytics() {
  const [period, setPeriod] = useState('30d');
  const [overview, setOverview] = useState(null);
  const [trends, setTrends] = useState(null);
  const [byType, setByType] = useState(null);
  const [byLO, setByLO] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  const fetchData = useCallback(async (selectedPeriod) => {
    setLoading(true);
    try {
      const [overviewRes, trendsRes, byTypeRes] = await Promise.all([
        calendarAnalyticsAPI.getOverview({ period: selectedPeriod }),
        calendarAnalyticsAPI.getTrends({ period: selectedPeriod, granularity: selectedPeriod === '7d' ? 'daily' : 'daily' }),
        calendarAnalyticsAPI.getByType({ period: selectedPeriod }),
      ]);

      setOverview(overviewRes);
      setTrends(trendsRes);
      setByType(byTypeRes);

      // Try fetching LO breakdown (admin-only endpoint)
      try {
        const byLORes = await calendarAnalyticsAPI.getByLO({ period: selectedPeriod });
        setByLO(byLORes);
        setIsAdmin(true);
      } catch {
        // Non-admin: silently skip
        setByLO(null);
        setIsAdmin(false);
      }
    } catch (err) {
      console.error('Analytics fetch failed:', err);
      toast.error('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(period);
  }, [period, fetchData]);

  const handlePeriodChange = useCallback((newPeriod) => {
    setPeriod(newPeriod);
  }, []);

  if (loading) {
    return (
      <div className="cal-analytics">
        <div className="cal-analytics__loading">
          <div className="cal-analytics__spinner" />
          <span>Loading analytics...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="cal-analytics">
      <div className="cal-analytics__header">
        <div className="cal-analytics__period-selector">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              className={`cal-analytics__period-btn ${period === p.key ? 'cal-analytics__period-btn--active' : ''}`}
              onClick={() => handlePeriodChange(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Cards */}
      {overview && <KPICards overview={overview} />}

      {/* Two-column grid: Trends + Type Distribution */}
      <div className="cal-analytics__grid-2col">
        {trends && <TrendChart trends={trends} period={period} />}
        {byType && <TypeBreakdown byType={byType} />}
      </div>

      {/* Heatmap */}
      {trends?.peak_hours && <Heatmap peakHours={trends.peak_hours} />}

      {/* LO Breakdown (admin only) */}
      {isAdmin && byLO && <LOBreakdown byLO={byLO} />}
    </div>
  );
}


// =============================================================================
// KPI Cards
// =============================================================================

function KPICards({ overview }) {
  const {
    total_appointments = 0,
    completion_rate = 0,
    avg_duration_minutes = 0,
    utilization_rate = 0,
    busiest_day_of_week,
    busiest_hour_label,
    no_shows = 0,
    cancelled = 0,
  } = overview;

  return (
    <div className="cal-analytics__kpis">
      <div className="cal-analytics__kpi">
        <p className="cal-analytics__kpi-label">Total Appointments</p>
        <p className="cal-analytics__kpi-value">{total_appointments}</p>
        <p className="cal-analytics__kpi-sub">
          {cancelled} cancelled, {no_shows} no-shows
        </p>
      </div>

      <div className="cal-analytics__kpi">
        <p className="cal-analytics__kpi-label">Completion Rate</p>
        <p className="cal-analytics__kpi-value">{completion_rate}%</p>
        <p className={`cal-analytics__kpi-sub ${completion_rate >= 80 ? 'cal-analytics__kpi-sub--positive' : completion_rate < 60 ? 'cal-analytics__kpi-sub--negative' : ''}`}>
          {completion_rate >= 80 ? 'On track' : completion_rate >= 60 ? 'Needs attention' : 'Below target'}
        </p>
      </div>

      <div className="cal-analytics__kpi">
        <p className="cal-analytics__kpi-label">Avg Duration</p>
        <p className="cal-analytics__kpi-value">{avg_duration_minutes}<span style={{ fontSize: 16, fontWeight: 400 }}> min</span></p>
        <p className="cal-analytics__kpi-sub">
          {busiest_day_of_week ? `Busiest: ${busiest_day_of_week}` : ''}
        </p>
      </div>

      <div className="cal-analytics__kpi">
        <p className="cal-analytics__kpi-label">Utilization</p>
        <p className="cal-analytics__kpi-value">{utilization_rate}%</p>
        <p className="cal-analytics__kpi-sub">
          {busiest_hour_label ? `Peak hour: ${busiest_hour_label}` : 'Booked / available hours'}
        </p>
      </div>
    </div>
  );
}


// =============================================================================
// Trend Chart (vertical bars)
// =============================================================================

function TrendChart({ trends, period }) {
  const { labels = [], datasets = {} } = trends;
  const totalData = datasets.total || [];
  const completedData = datasets.completed || [];
  const cancelledData = datasets.cancelled || [];

  const maxVal = useMemo(() => Math.max(...totalData, 1), [totalData]);

  if (!labels.length) {
    return (
      <div className="cal-analytics__section">
        <h2 className="cal-analytics__section-title">Appointment Trends</h2>
        <div className="cal-analytics__empty">No trend data available for this period</div>
      </div>
    );
  }

  // Format date labels
  const formatLabel = (iso) => {
    if (!iso) return '';
    const d = new Date(iso + 'T00:00:00');
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  // Limit displayed bars for readability
  const maxBars = period === '90d' ? 30 : labels.length;
  const step = Math.max(1, Math.ceil(labels.length / maxBars));
  const displayIndices = [];
  for (let i = 0; i < labels.length; i += step) {
    displayIndices.push(i);
  }

  return (
    <div className="cal-analytics__section">
      <h2 className="cal-analytics__section-title">Appointment Trends</h2>
      <div className="cal-analytics__trend-chart">
        {displayIndices.map((i) => {
          const total = totalData[i] || 0;
          const heightPct = (total / maxVal) * 100;
          return (
            <div key={i} className="cal-analytics__trend-bar-group">
              <div
                className="cal-analytics__trend-bar"
                style={{ '--bar-height': `${heightPct}%`, '--bar-color': '#3b82f6' }}
                data-tooltip={`${formatLabel(labels[i])}: ${total} appointments`}
              />
            </div>
          );
        })}
      </div>
      <div className="cal-analytics__trend-labels">
        {displayIndices.map((i) => (
          <span key={i} className="cal-analytics__trend-label">
            {i % Math.max(1, Math.ceil(displayIndices.length / 8)) === 0 ? formatLabel(labels[i]) : ''}
          </span>
        ))}
      </div>
      <div className="cal-analytics__legend">
        <span className="cal-analytics__legend-item">
          <span className="cal-analytics__legend-dot" style={{ background: '#3b82f6' }} />
          Total ({totalData.reduce((a, b) => a + b, 0)})
        </span>
        <span className="cal-analytics__legend-item">
          <span className="cal-analytics__legend-dot" style={{ background: '#22c55e' }} />
          Completed ({completedData.reduce((a, b) => a + b, 0)})
        </span>
        <span className="cal-analytics__legend-item">
          <span className="cal-analytics__legend-dot" style={{ background: '#ef4444' }} />
          Cancelled ({cancelledData.reduce((a, b) => a + b, 0)})
        </span>
      </div>
    </div>
  );
}


// =============================================================================
// Type Breakdown (horizontal bars)
// =============================================================================

function TypeBreakdown({ byType }) {
  const types = byType?.types || [];

  if (!types.length) {
    return (
      <div className="cal-analytics__section">
        <h2 className="cal-analytics__section-title">By Appointment Type</h2>
        <div className="cal-analytics__empty">No type data available</div>
      </div>
    );
  }

  const maxTotal = Math.max(...types.map((t) => t.total), 1);

  return (
    <div className="cal-analytics__section">
      <h2 className="cal-analytics__section-title">By Appointment Type</h2>
      <div className="cal-analytics__hbar-chart">
        {types.map((t) => (
          <div key={t.type_id || t.type_name} className="cal-analytics__hbar-row">
            <span className="cal-analytics__hbar-name" title={t.type_name}>
              {t.type_name}
            </span>
            <div className="cal-analytics__hbar-track">
              <div
                className="cal-analytics__hbar-fill"
                style={{
                  '--bar-width': `${(t.total / maxTotal) * 100}%`,
                  '--bar-color': t.color || '#3b82f6',
                }}
              >
                {t.total}
              </div>
            </div>
            <span className="cal-analytics__hbar-stats">
              {t.percentage}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}


// =============================================================================
// Heatmap (7 days x hours)
// =============================================================================

function Heatmap({ peakHours }) {
  const { grid = [], max_count = 0 } = peakHours;

  // Build a quick lookup: [day_index][hour] -> count
  const lookup = useMemo(() => {
    const map = {};
    for (const cell of grid) {
      if (!map[cell.day_index]) map[cell.day_index] = {};
      map[cell.day_index][cell.hour] = cell.count;
    }
    return map;
  }, [grid]);

  if (max_count === 0) {
    return (
      <div className="cal-analytics__section">
        <h2 className="cal-analytics__section-title">Busiest Hours</h2>
        <div className="cal-analytics__empty">No data available to build heatmap</div>
      </div>
    );
  }

  return (
    <div className="cal-analytics__section">
      <h2 className="cal-analytics__section-title">Busiest Hours</h2>
      <div className="cal-analytics__heatmap">
        <div
          className="cal-analytics__heatmap-grid"
          style={{ gridTemplateColumns: `60px repeat(${HEATMAP_HOURS.length}, 1fr)` }}
        >
          {/* Header row */}
          <div className="cal-analytics__heatmap-header" />
          {HEATMAP_HOURS.map((h) => (
            <div key={`h-${h}`} className="cal-analytics__heatmap-header">
              {HOUR_LABELS[h]}
            </div>
          ))}

          {/* Day rows */}
          {DAY_ABBREVS.map((dayName, dayIdx) => (
            <React.Fragment key={dayName}>
              <div className="cal-analytics__heatmap-day-label">{dayName}</div>
              {HEATMAP_HOURS.map((h) => {
                const count = (lookup[dayIdx] && lookup[dayIdx][h]) || 0;
                const intensity = max_count > 0 ? count / max_count : 0;
                return (
                  <div
                    key={`${dayIdx}-${h}`}
                    className="cal-analytics__heatmap-cell"
                    style={{ '--intensity': intensity }}
                    data-tooltip={`${dayName} ${HOUR_LABELS[h]}: ${count} appointments`}
                  />
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Scale legend */}
      <div className="cal-analytics__heatmap-scale">
        <span>Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map((intensity) => (
          <div
            key={intensity}
            className="cal-analytics__heatmap-scale-block"
            style={{
              background: `color-mix(in srgb, #3b82f6 ${intensity * 100}%, #f1f5f9)`,
            }}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}


// =============================================================================
// LO Breakdown Table (admin only)
// =============================================================================

function LOBreakdown({ byLO }) {
  const officers = byLO?.loan_officers || [];

  if (!officers.length) {
    return null;
  }

  const getUtilClass = (rate) => {
    if (rate >= 80) return 'cal-analytics__util-fill--high';
    if (rate >= 40) return '';
    if (rate >= 20) return 'cal-analytics__util-fill--low';
    return 'cal-analytics__util-fill--critical';
  };

  return (
    <div className="cal-analytics__section">
      <h2 className="cal-analytics__section-title">By Loan Officer</h2>
      <div style={{ overflowX: 'auto' }}>
        <table className="cal-analytics__lo-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Total</th>
              <th>Completed</th>
              <th>Cancelled</th>
              <th>No-Shows</th>
              <th>Completion</th>
              <th>Utilization</th>
            </tr>
          </thead>
          <tbody>
            {officers.map((lo) => (
              <tr key={lo.user_id}>
                <td>
                  <span className="cal-analytics__lo-name">{lo.name}</span>
                </td>
                <td>{lo.total}</td>
                <td>{lo.completed}</td>
                <td>{lo.cancelled}</td>
                <td>{lo.no_shows}</td>
                <td>{lo.completion_rate}%</td>
                <td>
                  <div className="cal-analytics__util-bar">
                    <div className="cal-analytics__util-track">
                      <div
                        className={`cal-analytics__util-fill ${getUtilClass(lo.utilization_rate)}`}
                        style={{ '--bar-width': `${Math.min(lo.utilization_rate, 100)}%` }}
                      />
                    </div>
                    <span>{lo.utilization_rate}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
