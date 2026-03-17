/**
 * Scheduler Conversion Analytics Dashboard
 *
 * Tracks the full appointment-to-funded-loan conversion funnel:
 * Booked -> Showed -> Lead -> Application -> Funded
 *
 * Sections:
 * - KPI summary cards
 * - Conversion funnel visualization
 * - Source performance bar chart
 * - Day/hour heatmap
 * - LO leaderboard table
 * - AI vs manual comparison
 * - Weekly trends line chart
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, Cell
} from 'recharts';
import { getAuthHeaders } from '../utils/auth';
import './SchedulerAnalytics.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------
function formatDateParam(d) {
  return d.toISOString().split('T')[0];
}

function getDefaultRange(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  return { start: formatDateParam(start), end: formatDateParam(end) };
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
function fmtCurrency(n) {
  if (n == null) return '$0';
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtPct(n) {
  if (n == null) return '0%';
  return Number(n).toFixed(1) + '%';
}

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------
const COLORS = {
  primary: '#218D8D',
  secondary: '#d97757',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  muted: '#94a3b8',
  purple: '#8b5cf6',
  blue: '#3b82f6',
};

const FUNNEL_COLORS = [COLORS.blue, COLORS.primary, COLORS.purple, COLORS.secondary, COLORS.success];

const SOURCE_COLORS = [COLORS.primary, COLORS.secondary, COLORS.purple, COLORS.blue, COLORS.success, COLORS.warning];

// Heatmap intensity (0..1 -> transparent teal to solid teal)
function heatColor(value, max) {
  if (!max || !value) return 'transparent';
  const intensity = Math.min(value / max, 1);
  return `rgba(33, 141, 141, ${0.1 + intensity * 0.8})`;
}

// ---------------------------------------------------------------------------
// Period selector
// ---------------------------------------------------------------------------
const PERIOD_OPTIONS = [
  { value: 30, label: '30 Days' },
  { value: 90, label: '90 Days' },
  { value: 180, label: '6 Months' },
  { value: 365, label: '1 Year' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const SchedulerAnalyticsDashboard = () => {
  const [period, setPeriod] = useState(90);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data slices
  const [funnel, setFunnel] = useState(null);
  const [sources, setSources] = useState(null);
  const [loPerf, setLoPerf] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [aiPerf, setAiPerf] = useState(null);
  const [trends, setTrends] = useState(null);

  // -----------------------------------------------------------
  // Fetch all analytics endpoints in parallel
  // -----------------------------------------------------------
  const loadData = useCallback(async (days) => {
    setLoading(true);
    setError(null);
    const { start, end } = getDefaultRange(days);
    const qs = `start_date=${start}&end_date=${end}`;
    const headers = getAuthHeaders();

    const endpoints = [
      { key: 'funnel', url: `/api/v1/scheduler/analytics/funnel?${qs}` },
      { key: 'sources', url: `/api/v1/scheduler/analytics/sources?${qs}` },
      { key: 'loPerf', url: `/api/v1/scheduler/analytics/lo-performance?${qs}` },
      { key: 'heatmap', url: `/api/v1/scheduler/analytics/time-heatmap?${qs}` },
      { key: 'revenue', url: `/api/v1/scheduler/analytics/revenue?${qs}` },
      { key: 'aiPerf', url: `/api/v1/scheduler/analytics/ai-performance?${qs}` },
      { key: 'trends', url: `/api/v1/scheduler/analytics/trends?${qs}` },
    ];

    try {
      const results = await Promise.allSettled(
        endpoints.map(ep =>
          fetch(`${API_BASE}${ep.url}`, { headers }).then(r => {
            if (!r.ok) throw new Error(`${ep.key}: ${r.status}`);
            return r.json();
          })
        )
      );

      const setters = { funnel: setFunnel, sources: setSources, loPerf: setLoPerf, heatmap: setHeatmap, revenue: setRevenue, aiPerf: setAiPerf, trends: setTrends };
      endpoints.forEach((ep, i) => {
        if (results[i].status === 'fulfilled') {
          setters[ep.key](results[i].value);
        }
      });

      // If all failed, show error
      const allFailed = results.every(r => r.status === 'rejected');
      if (allFailed) {
        setError('Failed to load analytics data. Please try again.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(period);
  }, [period, loadData]);

  // -----------------------------------------------------------
  // Derived data
  // -----------------------------------------------------------
  const funnelData = funnel?.funnel
    ? [
        { name: 'Booked', value: funnel.funnel.booked },
        { name: 'Showed', value: funnel.funnel.showed },
        { name: 'Lead', value: funnel.funnel.linked_lead },
        { name: 'Application', value: funnel.funnel.application },
        { name: 'Funded', value: funnel.funnel.funded },
      ]
    : [];

  const sourceData = sources?.sources || [];

  const trendData = (trends?.weeks || []).map(w => ({
    ...w,
    week: w.week_start ? w.week_start.slice(5) : '', // MM-DD
  }));

  // Heatmap grid: 7 days x 24 hours (but typically business hours 7-19)
  const heatmapSlots = heatmap?.heatmap || [];
  const heatmapMax = heatmapSlots.reduce((m, s) => Math.max(m, s.booked || 0), 0);
  const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const HOURS = Array.from({ length: 13 }, (_, i) => i + 7); // 7 AM to 7 PM

  // Build heatmap grid lookup
  const heatLookup = {};
  heatmapSlots.forEach(s => {
    heatLookup[`${s.day_index}-${s.hour}`] = s;
  });

  // -----------------------------------------------------------
  // Render
  // -----------------------------------------------------------
  if (loading) {
    return (
      <div className="sca-dashboard">
        <div className="sca-loading">
          <div className="sca-spinner" />
          <p>Loading conversion analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="sca-dashboard">
      {/* Header */}
      <div className="sca-header">
        <div className="sca-header-text">
          <h1>Appointment Conversion Analytics</h1>
          <p>Track the full funnel from appointment booking to funded loan</p>
        </div>
        <div className="sca-period-toggle">
          {PERIOD_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`sca-period-btn ${period === opt.value ? 'active' : ''}`}
              onClick={() => setPeriod(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="sca-error" role="alert">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* KPI Summary Cards */}
      {funnel && (
        <div className="sca-kpi-grid">
          <div className="sca-kpi-card">
            <div className="sca-kpi-value">{funnel.funnel.booked}</div>
            <div className="sca-kpi-label">Appointments</div>
          </div>
          <div className="sca-kpi-card">
            <div className="sca-kpi-value">{fmtPct(funnel.rates.show_rate)}</div>
            <div className="sca-kpi-label">Show Rate</div>
          </div>
          <div className="sca-kpi-card">
            <div className="sca-kpi-value">{fmtPct(funnel.rates.lead_conversion_rate)}</div>
            <div className="sca-kpi-label">Lead Conversion</div>
          </div>
          <div className="sca-kpi-card">
            <div className="sca-kpi-value">{fmtPct(funnel.rates.pull_through_rate)}</div>
            <div className="sca-kpi-label">Pull-Through</div>
          </div>
          <div className="sca-kpi-card accent">
            <div className="sca-kpi-value">{fmtCurrency(funnel.rates.revenue_per_appointment)}</div>
            <div className="sca-kpi-label">Revenue / Appt</div>
          </div>
          <div className="sca-kpi-card accent">
            <div className="sca-kpi-value">{funnel.funnel.funded_volume_formatted || fmtCurrency(funnel.funnel.funded_volume)}</div>
            <div className="sca-kpi-label">Funded Volume</div>
          </div>
        </div>
      )}

      {/* Two-column layout: Funnel + Source */}
      <div className="sca-two-col">
        {/* Conversion Funnel */}
        {funnelData.length > 0 && (
          <div className="sca-card">
            <h2>Conversion Funnel</h2>
            <div className="sca-funnel">
              {funnelData.map((step, i) => {
                const maxVal = funnelData[0].value || 1;
                const widthPct = Math.max((step.value / maxVal) * 100, 8);
                const rate = i > 0 && funnelData[i - 1].value > 0
                  ? ((step.value / funnelData[i - 1].value) * 100).toFixed(1)
                  : null;
                return (
                  <div key={step.name} className="sca-funnel-step">
                    <div className="sca-funnel-label">
                      <span>{step.name}</span>
                      <span className="sca-funnel-count">{step.value}</span>
                    </div>
                    <div className="sca-funnel-bar-track">
                      <div
                        className="sca-funnel-bar"
                        style={{
                          width: `${widthPct}%`,
                          backgroundColor: FUNNEL_COLORS[i % FUNNEL_COLORS.length],
                        }}
                      />
                    </div>
                    {rate && <span className="sca-funnel-rate">{rate}%</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Source Performance */}
        {sourceData.length > 0 && (
          <div className="sca-card">
            <h2>Source Performance</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={sourceData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="source" width={90} tick={{ fontSize: 12 }} />
                <Tooltip
                  formatter={(value, name) => {
                    if (name === 'funded_volume') return [fmtCurrency(value), 'Funded Volume'];
                    return [value, name.charAt(0).toUpperCase() + name.slice(1)];
                  }}
                />
                <Bar dataKey="booked" name="Booked" fill={COLORS.blue} />
                <Bar dataKey="showed" name="Showed" fill={COLORS.primary} />
                <Bar dataKey="funded" name="Funded" fill={COLORS.success} />
                <Legend />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Time Heatmap */}
      {heatmapSlots.length > 0 && (
        <div className="sca-card full-width">
          <h2>Appointment Time Heatmap</h2>
          <p className="sca-card-subtitle">Darker cells indicate more bookings. Hover for details.</p>
          <div className="sca-heatmap-wrapper">
            <table className="sca-heatmap">
              <thead>
                <tr>
                  <th></th>
                  {HOURS.map(h => (
                    <th key={h}>{h > 12 ? `${h - 12}p` : h === 12 ? '12p' : `${h}a`}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DAY_LABELS.map((day, di) => (
                  <tr key={day}>
                    <td className="sca-heatmap-day">{day}</td>
                    {HOURS.map(h => {
                      const slot = heatLookup[`${di}-${h}`];
                      const booked = slot?.booked || 0;
                      const showRate = slot?.show_rate || 0;
                      return (
                        <td
                          key={h}
                          className="sca-heatmap-cell"
                          style={{ backgroundColor: heatColor(booked, heatmapMax) }}
                          title={`${day} ${h}:00 - ${booked} booked, ${showRate}% show rate`}
                        >
                          {booked > 0 ? booked : ''}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {heatmap?.insights?.busiest_slot?.booked > 0 && (
            <p className="sca-insight">
              Busiest slot: <strong>{heatmap.insights.busiest_slot.day} {heatmap.insights.busiest_slot.hour}:00</strong> ({heatmap.insights.busiest_slot.booked} appointments)
            </p>
          )}
        </div>
      )}

      {/* LO Leaderboard */}
      {loPerf?.loan_officers?.length > 0 && (
        <div className="sca-card full-width">
          <h2>LO Conversion Leaderboard</h2>
          <div className="sca-table-wrapper">
            <table className="sca-table">
              <thead>
                <tr>
                  <th>Loan Officer</th>
                  <th>Booked</th>
                  <th>Showed</th>
                  <th>Show Rate</th>
                  <th>Leads</th>
                  <th>Applications</th>
                  <th>Funded</th>
                  <th>Funded Volume</th>
                  <th>Overall Rate</th>
                  <th>Rev / Appt</th>
                </tr>
              </thead>
              <tbody>
                {loPerf.loan_officers.map((lo, i) => (
                  <tr key={lo.lo_id || i}>
                    <td className="sca-lo-name">
                      <span className="sca-rank">{i + 1}</span>
                      {lo.lo_name}
                    </td>
                    <td>{lo.booked}</td>
                    <td>{lo.showed}</td>
                    <td className={lo.show_rate >= 80 ? 'text-success' : lo.show_rate < 50 ? 'text-danger' : ''}>
                      {fmtPct(lo.show_rate)}
                    </td>
                    <td>{lo.leads}</td>
                    <td>{lo.applications}</td>
                    <td>{lo.funded}</td>
                    <td>{fmtCurrency(lo.funded_volume)}</td>
                    <td className={lo.overall_rate >= 15 ? 'text-success' : ''}>
                      {fmtPct(lo.overall_rate)}
                    </td>
                    <td>{fmtCurrency(lo.revenue_per_appointment)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Two-column: AI vs Manual + Revenue */}
      <div className="sca-two-col">
        {/* AI vs Manual */}
        {aiPerf && (aiPerf.ai || aiPerf.manual) && (
          <div className="sca-card">
            <h2>AI vs Manual Booking</h2>
            <div className="sca-comparison">
              {['ai', 'manual'].map(type => {
                const data = aiPerf[type];
                if (!data) return (
                  <div key={type} className="sca-comparison-col">
                    <h3>{type === 'ai' ? 'AI Booked' : 'Manually Booked'}</h3>
                    <p className="sca-no-data">No data</p>
                  </div>
                );
                return (
                  <div key={type} className="sca-comparison-col">
                    <h3>{type === 'ai' ? 'AI Booked' : 'Manually Booked'}</h3>
                    <div className="sca-comparison-stat">
                      <span className="label">Booked</span>
                      <span className="value">{data.booked}</span>
                    </div>
                    <div className="sca-comparison-stat">
                      <span className="label">Show Rate</span>
                      <span className={`value ${aiPerf.insights?.higher_show_rate === type ? 'winner' : ''}`}>
                        {fmtPct(data.show_rate)}
                      </span>
                    </div>
                    <div className="sca-comparison-stat">
                      <span className="label">Conversion</span>
                      <span className={`value ${aiPerf.insights?.higher_conversion === type ? 'winner' : ''}`}>
                        {fmtPct(data.overall_conversion)}
                      </span>
                    </div>
                    <div className="sca-comparison-stat">
                      <span className="label">Rev / Appt</span>
                      <span className={`value ${aiPerf.insights?.higher_revenue_per_appt === type ? 'winner' : ''}`}>
                        {fmtCurrency(data.revenue_per_appointment)}
                      </span>
                    </div>
                    <div className="sca-comparison-stat">
                      <span className="label">Avg Days to Fund</span>
                      <span className="value">{data.avg_days_to_fund || '--'}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Revenue Attribution */}
        {revenue?.summary && (
          <div className="sca-card">
            <h2>Revenue Attribution</h2>
            <div className="sca-revenue-stats">
              <div className="sca-revenue-stat">
                <div className="sca-revenue-value">{revenue.summary.total_funded_volume_formatted || fmtCurrency(revenue.summary.total_funded_volume)}</div>
                <div className="sca-revenue-label">Total Funded from Appointments</div>
              </div>
              <div className="sca-revenue-stat">
                <div className="sca-revenue-value">{fmtCurrency(revenue.summary.avg_funded_amount)}</div>
                <div className="sca-revenue-label">Avg Funded Loan</div>
              </div>
              <div className="sca-revenue-stat">
                <div className="sca-revenue-value">{revenue.summary.avg_days_to_fund || '--'} days</div>
                <div className="sca-revenue-label">Avg Time to Fund</div>
              </div>
              <div className="sca-revenue-stat">
                <div className="sca-revenue-value">{fmtPct(revenue.summary.conversion_rate)}</div>
                <div className="sca-revenue-label">Appointment-to-Fund Rate</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Weekly Trends */}
      {trendData.length > 1 && (
        <div className="sca-card full-width">
          <h2>Weekly Trends</h2>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="week" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 12 }} unit="%" />
              <Tooltip
                formatter={(value, name) => {
                  if (name === 'show_rate' || name === 'conversion_rate') return [fmtPct(value), name.replace(/_/g, ' ')];
                  if (name === 'funded_volume') return [fmtCurrency(value), 'Funded Volume'];
                  return [value, name.replace(/_/g, ' ')];
                }}
              />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="booked" stroke={COLORS.blue} strokeWidth={2} name="Booked" dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="showed" stroke={COLORS.primary} strokeWidth={2} name="Showed" dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="funded" stroke={COLORS.success} strokeWidth={2} name="Funded" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="show_rate" stroke={COLORS.secondary} strokeWidth={2} strokeDasharray="5 5" name="Show Rate %" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Revenue Monthly Trend */}
      {revenue?.monthly_trend?.length > 1 && (
        <div className="sca-card full-width">
          <h2>Monthly Revenue from Appointments</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={revenue.monthly_trend} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} tickFormatter={v => fmtCurrency(v)} />
              <Tooltip formatter={(value, name) => {
                if (name === 'volume') return [fmtCurrency(value), 'Funded Volume'];
                return [value, name];
              }} />
              <Bar dataKey="volume" name="Funded Volume" fill={COLORS.primary} radius={[4, 4, 0, 0]}>
                {(revenue.monthly_trend || []).map((_, i) => (
                  <Cell key={i} fill={i % 2 === 0 ? COLORS.primary : '#2aa3a3'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default SchedulerAnalyticsDashboard;
