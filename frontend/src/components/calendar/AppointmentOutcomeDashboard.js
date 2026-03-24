/**
 * Appointment Outcome Dashboard
 * Shows whether AI-scheduled appointments lead to funded loans.
 * Provides the feedback loop missing from the scheduling intelligence system.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';

function AppointmentOutcomeDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(90);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [outcomes, typeEffectiveness] = await Promise.all([
        fetch(`/api/v1/scheduler/analytics/appointment-outcomes?days=${period}`).then(r => r.ok ? r.json() : null),
        fetch(`/api/v1/scheduler/analytics/appointment-type-effectiveness?days=${period}`).then(r => r.ok ? r.json() : null),
      ]);
      setData({ outcomes, typeEffectiveness });
    } catch (err) {
      console.error('Failed to load outcome data:', err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { loadData(); }, [loadData]);

  const handlePeriodChange = useCallback((e) => {
    setPeriod(Number(e.target.value));
  }, []);

  const o = data?.outcomes;

  const roiMetrics = useMemo(() => {
    if (!o) return null;
    return {
      additionalFunded: o.ai_scheduled?.funded || 0,
      fundedVolume: ((o.ai_scheduled?.funded_volume || 0) / 1000000).toFixed(1),
      daysFaster: Math.max(0, (o.manually_scheduled?.avg_days_to_fund || 0) - (o.ai_scheduled?.avg_days_to_fund || 0)).toFixed(0),
    };
  }, [o]);

  const typeEffectivenessTypes = useMemo(() => data?.typeEffectiveness?.types || [], [data?.typeEffectiveness]);

  if (loading) return <div style={{ padding: 20 }}>Loading outcome data...</div>;
  if (!o) return <div style={{ padding: 20, color: '#94a3b8' }}>No outcome data available yet.</div>;

  return (
    <div className="outcome-dashboard">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Scheduling ROI</h2>
        <select value={period} onChange={handlePeriodChange}
          style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={180}>Last 6 months</option>
        </select>
      </div>

      {/* AI vs Manual Comparison */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <ComparisonCard
          title="AI-Scheduled"
          appointments={o.ai_scheduled?.total || 0}
          funded={o.ai_scheduled?.funded || 0}
          conversionRate={o.ai_scheduled?.conversion_rate || 0}
          noShowRate={o.ai_scheduled?.no_show_rate || 0}
          avgDaysToFund={o.ai_scheduled?.avg_days_to_fund || 0}
          highlight={true}
        />
        <ComparisonCard
          title="Manually Scheduled"
          appointments={o.manually_scheduled?.total || 0}
          funded={o.manually_scheduled?.funded || 0}
          conversionRate={o.manually_scheduled?.conversion_rate || 0}
          noShowRate={o.manually_scheduled?.no_show_rate || 0}
          avgDaysToFund={o.manually_scheduled?.avg_days_to_fund || 0}
        />
      </div>

      {/* ROI Summary */}
      <div style={{
        background: '#eef2ff', borderRadius: 12, padding: 20, marginBottom: 24,
        border: '1px solid #c7d2fe',
      }}>
        <h3 style={{ margin: '0 0 12px', color: '#4338ca' }}>AI Scheduling Impact</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <div>
            <div style={{ fontSize: '0.8rem', color: '#6366f1' }}>Additional Funded Loans</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#4338ca' }}>
              {roiMetrics.additionalFunded}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.8rem', color: '#6366f1' }}>Funded Volume (AI)</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#4338ca' }}>
              ${roiMetrics.fundedVolume}M
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.8rem', color: '#6366f1' }}>Days Faster to Fund</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#4338ca' }}>
              {roiMetrics.daysFaster}
            </div>
          </div>
        </div>
      </div>

      {/* Type Effectiveness */}
      {typeEffectivenessTypes.length > 0 && (
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20 }}>
          <h3 style={{ margin: '0 0 12px' }}>Effectiveness by Appointment Type</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #e2e8f0', fontSize: '0.8rem' }}>Type</th>
                <th style={{ textAlign: 'right', padding: 8, borderBottom: '2px solid #e2e8f0', fontSize: '0.8rem' }}>Appointments</th>
                <th style={{ textAlign: 'right', padding: 8, borderBottom: '2px solid #e2e8f0', fontSize: '0.8rem' }}>Conversion</th>
                <th style={{ textAlign: 'right', padding: 8, borderBottom: '2px solid #e2e8f0', fontSize: '0.8rem' }}>No-Show %</th>
              </tr>
            </thead>
            <tbody>
              {typeEffectivenessTypes.map((t) => (
                <tr key={t.type_id || t.name}>
                  <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9' }}>{t.name}</td>
                  <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', textAlign: 'right' }}>{t.count}</td>
                  <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', textAlign: 'right', color: t.conversion > 30 ? '#22c55e' : '#64748b' }}>{t.conversion}%</td>
                  <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', textAlign: 'right', color: t.no_show > 20 ? '#ef4444' : '#64748b' }}>{t.no_show}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const ComparisonCard = React.memo(function ComparisonCard({ title, appointments, funded, conversionRate, noShowRate, avgDaysToFund, highlight }) {
  return (
    <div style={{
      background: highlight ? '#eef2ff' : '#f8fafc',
      border: `1px solid ${highlight ? '#c7d2fe' : '#e2e8f0'}`,
      borderRadius: 12,
      padding: 20,
    }}>
      <h4 style={{ margin: '0 0 12px', color: highlight ? '#4338ca' : '#1e293b' }}>{title}</h4>
      <div style={{ fontSize: '0.85rem', color: '#64748b', lineHeight: 2 }}>
        <div>Total: <strong>{appointments}</strong></div>
        <div>Funded: <strong style={{ color: '#22c55e' }}>{funded}</strong></div>
        <div>Conversion: <strong>{conversionRate}%</strong></div>
        <div>No-Show Rate: <strong style={{ color: noShowRate > 15 ? '#ef4444' : '#22c55e' }}>{noShowRate}%</strong></div>
        <div>Avg Days to Fund: <strong>{avgDaysToFund}</strong></div>
      </div>
    </div>
  );
});

export default React.memo(AppointmentOutcomeDashboard);
