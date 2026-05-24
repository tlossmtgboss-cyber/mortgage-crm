/**
 * Rate Monitor V2 — "Portfolio Heat Map"
 *
 * Two-column layout: left panel shows all monitored loans as a heat map
 * (colored by proximity to target rate), right panel shows rate details
 * and AI recommendations. Click a loan to see its refi math.
 * Optimized for: Managers overseeing large loan portfolios.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';

const PRODUCTS = {
  '30_fixed': '30 Yr Fixed',
  '15_fixed': '15 Yr Fixed',
  '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM',
  '30_fha': '30 Yr FHA',
  '30_va': '30 Yr VA',
};

export default function RateMonitorV2() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes, oppsRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
        fetch(`${API_BASE}/opportunities?limit=100`, { credentials: 'include' }),
      ]);
      if (ratesRes.ok) setRates(await ratesRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
      if (oppsRes.ok) {
        const data = await oppsRes.json();
        setOpportunities(data);
        if (data.length > 0 && !selectedOpp) setSelectedOpp(data[0]);
      }
    } catch (e) {
      console.error('Rate watch fetch:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div style={styles.page}><div style={styles.skeleton} /></div>;

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.title}>Portfolio Rate Monitor</h1>
        <div style={styles.rateChips}>
          {rates?.rates?.slice(0, 3).map(r => (
            <div key={r.product} style={styles.rateChip}>
              <span style={styles.chipLabel}>{PRODUCTS[r.product]}</span>
              <span style={styles.chipValue}>{formatRate(r.perennia_rate)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Summary Bar */}
      <div style={styles.summaryBar}>
        <SummaryPill label="Monitored" value={summary?.active_targets || 0} />
        <SummaryPill label="Triggered" value={summary?.pending_opportunities || 0} color="#B8924A" />
        <SummaryPill label="Savings Pool" value={formatCurrency(summary?.total_potential_savings)} color="#2D7A52" />
        <SummaryPill label="Today" value={summary?.alerts_today || 0} color={summary?.alerts_today > 0 ? '#9B2C2C' : undefined} />
      </div>

      {/* Two Column Layout */}
      <div style={styles.columns}>
        {/* Left: Heat Map List */}
        <div style={styles.leftPanel}>
          <div style={styles.panelHeader}>
            <h3 style={styles.panelTitle}>Opportunity Heat Map</h3>
            <span style={styles.panelCount}>{opportunities.length} active</span>
          </div>
          <div style={styles.heatList}>
            {opportunities.length === 0 ? (
              <div style={styles.emptyHeat}>
                <p style={styles.emptyText}>No opportunities detected yet.</p>
                <p style={styles.emptySubtext}>Rates are being monitored — matches will appear as borrower targets are hit.</p>
              </div>
            ) : (
              opportunities.map(opp => (
                <div
                  key={opp.id}
                  style={{
                    ...styles.heatRow,
                    ...(selectedOpp?.id === opp.id ? styles.heatRowActive : {}),
                    borderLeftColor: getHeatColor(opp),
                  }}
                  onClick={() => setSelectedOpp(opp)}
                >
                  <div style={styles.heatRowMain}>
                    <span style={styles.heatBorrower}>Loan #{opp.loan_id}</span>
                    <span style={styles.heatProduct}>{PRODUCTS[opp.product]}</span>
                  </div>
                  <div style={styles.heatRowSub}>
                    <span style={styles.heatSavings}>{formatCurrency(opp.monthly_savings)}/mo</span>
                    <span style={styles.heatStatus}>{opp.status}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Detail Panel */}
        <div style={styles.rightPanel}>
          {selectedOpp ? (
            <OpportunityDetail opp={selectedOpp} rates={rates} />
          ) : (
            <div style={styles.noSelection}>
              <p style={styles.noSelectionText}>Select an opportunity to view refi math and AI recommendation</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryPill({ label, value, color }) {
  return (
    <div style={styles.pill}>
      <span style={styles.pillLabel}>{label}</span>
      <span style={{ ...styles.pillValue, color: color || '#1A1F1B' }}>{value}</span>
    </div>
  );
}

function OpportunityDetail({ opp, rates }) {
  const currentRate = rates?.rates?.find(r => r.product === opp.product);

  return (
    <div style={styles.detailPanel}>
      <div style={styles.detailHeader}>
        <h3 style={styles.detailTitle}>Loan #{opp.loan_id}</h3>
        <span style={{
          ...styles.detailStatus,
          background: opp.status === 'detected' ? '#DFF0E3' : '#FEF3C7',
          color: opp.status === 'detected' ? '#2D7A52' : '#B25F18',
        }}>{opp.status}</span>
      </div>

      {/* Rate Comparison */}
      <div style={styles.rateComparison}>
        <div style={styles.rateBox}>
          <span style={styles.rateBoxLabel}>Current Loan Rate</span>
          <span style={styles.rateBoxValue}>{formatRate(opp.current_rate)}</span>
        </div>
        <div style={styles.rateArrow}>→</div>
        <div style={{ ...styles.rateBox, borderColor: '#2D7A52' }}>
          <span style={styles.rateBoxLabel}>Perennia Rate</span>
          <span style={{ ...styles.rateBoxValue, color: '#2D7A52' }}>{formatRate(opp.perennia_rate)}</span>
        </div>
      </div>

      {/* Savings Math */}
      <div style={styles.mathGrid}>
        <MathRow label="Current Payment" value={formatCurrency(opp.current_payment)} />
        <MathRow label="Projected Payment" value={formatCurrency(opp.projected_payment)} />
        <MathRow label="Monthly Savings" value={formatCurrency(opp.monthly_savings)} highlight />
        <MathRow label="Balance" value={formatCurrency(opp.current_balance)} />
        {opp.estimated_break_even_months && (
          <MathRow label="Break-Even" value={`${opp.estimated_break_even_months} months`} />
        )}
        <MathRow label="Margin Applied" value={`${opp.margin_bps_at_detection} bps`} />
      </div>

      {/* AI Recommendation */}
      <div style={styles.aiBox}>
        <div style={styles.aiHeader}>
          <span style={styles.aiIcon}>🤖</span>
          <span style={styles.aiTitle}>Aria's Recommendation</span>
        </div>
        <p style={styles.aiText}>
          This borrower's target rate has been hit. With {formatCurrency(opp.monthly_savings)}/month in savings
          and a {opp.estimated_break_even_months || '—'}-month break-even, this is a strong refi candidate.
          Recommend immediate outreach via preferred channel.
        </p>
        {opp.status === 'detected' && (
          <button style={styles.aiAction}>Trigger Aria Outreach</button>
        )}
      </div>
    </div>
  );
}

function MathRow({ label, value, highlight }) {
  return (
    <div style={styles.mathRow}>
      <span style={styles.mathLabel}>{label}</span>
      <span style={{
        ...styles.mathValue,
        ...(highlight ? { color: '#2D7A52', fontWeight: 700 } : {}),
      }}>{value}</span>
    </div>
  );
}

function getHeatColor(opp) {
  const savings = parseFloat(opp.monthly_savings) || 0;
  if (savings >= 300) return '#2D7A52';
  if (savings >= 150) return '#B8924A';
  return '#ECE6D8';
}

function formatRate(val) {
  if (!val) return '—';
  const n = parseFloat(val);
  return isNaN(n) ? val : `${n.toFixed(2)}%`;
}

function formatCurrency(val) {
  if (!val && val !== 0) return '$0';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

const styles = {
  page: {
    padding: '32px 40px',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
  },
  skeleton: { height: 400, borderRadius: 12, background: '#F2EDE2' },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 28,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  rateChips: { display: 'flex', gap: 8 },
  rateChip: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '8px 16px',
    background: '#1F3D2E',
    borderRadius: 8,
  },
  chipLabel: { fontSize: 9, color: 'rgba(245,242,233,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' },
  chipValue: { fontSize: 15, fontWeight: 700, color: '#F5F2E9', fontFamily: "'Geist Mono', monospace" },
  summaryBar: {
    display: 'flex',
    gap: 12,
    marginBottom: 24,
    padding: '12px 20px',
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
  },
  pill: { display: 'flex', flexDirection: 'column', flex: 1 },
  pillLabel: { fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.05em' },
  pillValue: { fontSize: 20, fontWeight: 700, fontFamily: "'Fraunces', Georgia, serif" },
  columns: {
    display: 'grid',
    gridTemplateColumns: '380px 1fr',
    gap: 24,
    minHeight: 500,
  },
  leftPanel: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  },
  panelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 20px',
    borderBottom: '1px solid #ECE6D8',
  },
  panelTitle: { fontSize: 14, fontWeight: 600, color: '#1A1F1B', margin: 0 },
  panelCount: { fontSize: 11, color: '#8B8A7E' },
  heatList: { flex: 1, overflow: 'auto', padding: '8px 0' },
  emptyHeat: { padding: 32, textAlign: 'center' },
  emptyText: { color: '#4F554E', fontSize: 14, margin: '0 0 8px' },
  emptySubtext: { color: '#8B8A7E', fontSize: 12 },
  heatRow: {
    padding: '12px 20px',
    borderLeft: '4px solid transparent',
    cursor: 'pointer',
    transition: 'background 0.15s',
    marginBottom: 1,
  },
  heatRowActive: { background: '#F6F2EA' },
  heatRowMain: { display: 'flex', justifyContent: 'space-between', marginBottom: 4 },
  heatBorrower: { fontSize: 13, fontWeight: 600, color: '#1A1F1B' },
  heatProduct: { fontSize: 11, color: '#8B8A7E' },
  heatRowSub: { display: 'flex', justifyContent: 'space-between' },
  heatSavings: { fontSize: 12, color: '#2D7A52', fontWeight: 600 },
  heatStatus: { fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase' },
  rightPanel: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 24,
    overflow: 'auto',
  },
  noSelection: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' },
  noSelectionText: { color: '#8B8A7E', fontSize: 14 },
  detailPanel: {},
  detailHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  detailTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 600, color: '#1A1F1B', margin: 0 },
  detailStatus: { fontSize: 10, fontWeight: 700, padding: '4px 10px', borderRadius: 9999, textTransform: 'uppercase' },
  rateComparison: { display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 },
  rateBox: {
    flex: 1,
    padding: 16,
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    textAlign: 'center',
  },
  rateBoxLabel: { display: 'block', fontSize: 11, color: '#8B8A7E', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' },
  rateBoxValue: { fontSize: 28, fontWeight: 700, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  rateArrow: { fontSize: 24, color: '#B5B2A4' },
  mathGrid: { marginBottom: 24 },
  mathRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '10px 0',
    borderBottom: '1px solid #F2EDE2',
  },
  mathLabel: { fontSize: 13, color: '#4F554E' },
  mathValue: { fontSize: 13, fontWeight: 500, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  aiBox: {
    background: 'linear-gradient(160deg, #E5EDE6 0%, #FFFFFF 60%)',
    border: '1px solid #D8E8DC',
    borderRadius: 10,
    padding: 20,
  },
  aiHeader: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 },
  aiIcon: { fontSize: 18 },
  aiTitle: { fontSize: 13, fontWeight: 600, color: '#1F3D2E' },
  aiText: { fontSize: 13, color: '#4F554E', lineHeight: 1.5, margin: '0 0 16px' },
  aiAction: {
    padding: '10px 20px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  },
};
