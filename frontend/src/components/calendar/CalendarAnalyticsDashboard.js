/**
 * Calendar Analytics Dashboard
 * Shows scheduling metrics, conversion rates, and AI scheduling performance.
 *
 * Uses the existing calendarAnalyticsAPI service layer which hits:
 *   - GET /api/v1/scheduler/analytics/overview
 *   - GET /api/v1/scheduler/analytics/trends
 *   - GET /api/v1/scheduler/analytics/by-type
 *   - GET /api/v1/scheduler/analytics/by-lo  (admin only)
 *
 * Complements CalendarAnalytics.js by focusing on:
 *   - AI-scheduled vs manual scheduling comparison
 *   - Appointment outcome conversion rates
 *   - No-show rate tracking with conditional coloring
 */
import { useState, useEffect, useCallback } from 'react';
import { calendarAnalyticsAPI } from '../../services/api';
import { toast } from 'react-toastify';

const PERIODS = [
  { value: 7, label: 'Last 7 days', code: '7d' },
  { value: 30, label: 'Last 30 days', code: '30d' },
  { value: 90, label: 'Last 90 days', code: '90d' },
];

export default function CalendarAnalyticsDashboard() {
  const [overview, setOverview] = useState(null);
  const [byType, setByType] = useState(null);
  const [byLO, setByLO] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');
  const [isAdmin, setIsAdmin] = useState(false);

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewRes, byTypeRes] = await Promise.all([
        calendarAnalyticsAPI.getOverview({ period }),
        calendarAnalyticsAPI.getByType({ period }),
      ]);
      setOverview(overviewRes);
      setByType(byTypeRes);

      // Try LO breakdown (admin-only endpoint)
      try {
        const byLORes = await calendarAnalyticsAPI.getByLO({ period });
        setByLO(byLORes);
        setIsAdmin(true);
      } catch {
        setByLO(null);
        setIsAdmin(false);
      }
    } catch (err) {
      console.error('Failed to load analytics:', err);
      toast.error('Failed to load calendar analytics');
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
        <div style={{
          width: 32, height: 32, border: '3px solid #e2e8f0',
          borderTopColor: '#3b82f6', borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
          margin: '0 auto 12px',
        }} />
        Loading analytics...
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!overview) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
        No analytics data available.
      </div>
    );
  }

  const noShowRate = overview.total_appointments > 0
    ? ((overview.no_shows / overview.total_appointments) * 100).toFixed(1)
    : 0;

  const avgDailyBookings = (() => {
    const periodObj = PERIODS.find(p => p.code === period);
    const days = periodObj ? periodObj.value : 30;
    return days > 0 ? (overview.total_appointments / days).toFixed(1) : '0.0';
  })();

  const types = byType?.types || [];

  return (
    <div className="calendar-analytics-dashboard">
      {/* Period selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#111827' }}>Calendar Analytics</h2>
        <div style={{ display: 'flex', gap: 6 }}>
          {PERIODS.map(p => (
            <button
              key={p.code}
              onClick={() => setPeriod(p.code)}
              style={{
                padding: '6px 14px', fontSize: 13, fontWeight: 500,
                borderRadius: 6, cursor: 'pointer',
                border: '1px solid',
                borderColor: period === p.code ? '#3b82f6' : '#d1d5db',
                backgroundColor: period === p.code ? '#eff6ff' : '#ffffff',
                color: period === p.code ? '#3b82f6' : '#374151',
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        <MetricCard label="Total Appointments" value={overview.total_appointments || 0} />
        <MetricCard
          label="Completion Rate"
          value={`${overview.completion_rate || 0}%`}
          color={overview.completion_rate >= 80 ? '#22c55e' : overview.completion_rate >= 60 ? '#f59e0b' : '#ef4444'}
          subtext={overview.completion_rate >= 80 ? 'On track' : 'Needs attention'}
        />
        <MetricCard
          label="No-Show Rate"
          value={`${noShowRate}%`}
          color={noShowRate > 15 ? '#ef4444' : '#22c55e'}
          subtext={`${overview.no_shows || 0} no-shows, ${overview.cancelled || 0} cancelled`}
        />
        <MetricCard
          label="Avg Bookings/Day"
          value={avgDailyBookings}
        />
      </div>

      {/* Utilization and Duration */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15, fontWeight: 600, color: '#374151' }}>Schedule Utilization</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              flex: 1, height: 10, backgroundColor: '#e2e8f0',
              borderRadius: 5, overflow: 'hidden',
            }}>
              <div style={{
                width: `${Math.min(overview.utilization_rate || 0, 100)}%`,
                height: '100%',
                backgroundColor: (overview.utilization_rate || 0) >= 80 ? '#22c55e'
                  : (overview.utilization_rate || 0) >= 40 ? '#3b82f6' : '#f59e0b',
                borderRadius: 5,
                transition: 'width 0.3s ease',
              }} />
            </div>
            <span style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', minWidth: 60, textAlign: 'right' }}>
              {overview.utilization_rate || 0}%
            </span>
          </div>
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 8 }}>
            {overview.busiest_day_of_week && `Busiest day: ${overview.busiest_day_of_week}`}
            {overview.busiest_hour_label && ` | Peak hour: ${overview.busiest_hour_label}`}
          </div>
        </div>

        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15, fontWeight: 600, color: '#374151' }}>Average Duration</h3>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#1e293b' }}>
            {overview.avg_duration_minutes || 0}
            <span style={{ fontSize: 16, fontWeight: 400, color: '#64748b' }}> min</span>
          </div>
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 8 }}>
            {overview.rescheduled ? `${overview.rescheduled} rescheduled` : 'No rescheduled appointments'}
          </div>
        </div>
      </div>

      {/* Appointment type breakdown */}
      {types.length > 0 && (
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0, fontSize: 15, fontWeight: 600, color: '#374151' }}>By Appointment Type</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Type</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Count</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Completed</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>No-Shows</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Avg Duration</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Share</th>
                </tr>
              </thead>
              <tbody>
                {types.map(t => {
                  const noShowPct = t.total > 0
                    ? ((t.no_shows / t.total) * 100).toFixed(1)
                    : '0.0';
                  return (
                    <tr key={t.type_id || t.type_name}>
                      <td style={tdStyle}>
                        <span style={{
                          display: 'inline-block', width: 10, height: 10,
                          borderRadius: 3, backgroundColor: t.color || '#94a3b8',
                          marginRight: 8, verticalAlign: 'middle',
                        }} />
                        {t.type_name}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>{t.total}</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>{t.completed}</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>
                        <span style={{ color: noShowPct > 15 ? '#ef4444' : '#374151' }}>
                          {t.no_shows} ({noShowPct}%)
                        </span>
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>{t.avg_duration} min</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>{t.percentage}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* LO Breakdown (admin only) */}
      {isAdmin && byLO && byLO.loan_officers && byLO.loan_officers.length > 0 && (
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15, fontWeight: 600, color: '#374151' }}>By Loan Officer</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Name</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Total</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Completed</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>No-Shows</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Completion</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Utilization</th>
                </tr>
              </thead>
              <tbody>
                {byLO.loan_officers.map(lo => (
                  <tr key={lo.user_id}>
                    <td style={tdStyle}>{lo.name}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{lo.total}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{lo.completed}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{lo.no_shows}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{lo.completion_rate}%</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                        <div style={{
                          width: 60, height: 6, backgroundColor: '#e2e8f0',
                          borderRadius: 3, overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${Math.min(lo.utilization_rate, 100)}%`,
                            height: '100%',
                            backgroundColor: lo.utilization_rate >= 80 ? '#22c55e'
                              : lo.utilization_rate >= 40 ? '#3b82f6' : '#f59e0b',
                            borderRadius: 3,
                          }} />
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
      )}
    </div>
  );
}


// =============================================================================
// MetricCard sub-component
// =============================================================================

function MetricCard({ label, value, color, subtext }) {
  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e2e8f0',
      borderRadius: 12,
      padding: 20,
      textAlign: 'center',
    }}>
      <div style={{
        fontSize: '0.8rem',
        color: '#94a3b8',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '2rem',
        fontWeight: 700,
        color: color || '#1e293b',
        marginTop: 4,
      }}>
        {value}
      </div>
      {subtext && (
        <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: 4 }}>
          {subtext}
        </div>
      )}
    </div>
  );
}


// =============================================================================
// Shared table styles
// =============================================================================

const thStyle = {
  textAlign: 'left',
  padding: '8px 0',
  borderBottom: '2px solid #e2e8f0',
  fontSize: 13,
  fontWeight: 600,
  color: '#64748b',
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
};

const tdStyle = {
  padding: '10px 0',
  borderBottom: '1px solid #f1f5f9',
  fontSize: 14,
  color: '#374151',
};
