/**
 * Rate Monitor V7 — "Kanban Pipeline"
 *
 * Opportunities displayed as draggable-looking cards in Kanban columns
 * (Detected → Outreach → Responded → Meeting → Closed). Rates shown
 * as a compact header. Pipeline velocity metrics at top.
 * Optimized for: Sales-minded LOs who think in terms of deal flow.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

const COLUMNS = [
  { key: 'detected', label: 'Detected', color: '#B8924A', bg: '#FEF3C7' },
  { key: 'outreach_sent', label: 'Outreach', color: '#1F3D2E', bg: '#E5EDE6' },
  { key: 'borrower_responded', label: 'Responded', color: '#2D7A52', bg: '#DFF0E3' },
  { key: 'meeting_booked', label: 'Meeting', color: '#1F3D2E', bg: '#D8E8DC' },
  { key: 'closed_won', label: 'Won', color: '#2D7A52', bg: '#DFF0E3' },
];

export default function RateMonitorV7() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes, oppsRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
        fetch(`${API_BASE}/opportunities?limit=200`, { credentials: 'include' }),
      ]);
      if (ratesRes.ok) setRates(await ratesRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
      if (oppsRes.ok) setOpportunities(await oppsRes.json());
    } catch (e) {
      console.error('Fetch error:', e);
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
      {/* Header with rates */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <h1 style={styles.title}>Refi Pipeline</h1>
          <p style={styles.subtitle}>AI-detected opportunities flowing through outreach</p>
        </div>
        <div style={styles.headerRates}>
          {rates?.rates?.slice(0, 3).map(r => (
            <span key={r.product} style={styles.headerRate}>
              {PRODUCTS[r.product]?.split(' ')[0]} <strong>{formatRate(r.perennia_rate)}</strong>
            </span>
          ))}
        </div>
      </div>

      {/* Velocity Metrics */}
      <div style={styles.velocity}>
        <div style={styles.velItem}>
          <span style={styles.velNum}>{summary?.pending_opportunities || 0}</span>
          <span style={styles.velLabel}>In Pipeline</span>
        </div>
        <div style={styles.velDivider} />
        <div style={styles.velItem}>
          <span style={{ ...styles.velNum, color: '#B8924A' }}>{formatCurrency(summary?.total_potential_savings)}</span>
          <span style={styles.velLabel}>Monthly Savings Potential</span>
        </div>
        <div style={styles.velDivider} />
        <div style={styles.velItem}>
          <span style={styles.velNum}>{summary?.alerts_today || 0}</span>
          <span style={styles.velLabel}>New Today</span>
        </div>
        <div style={styles.velDivider} />
        <div style={styles.velItem}>
          <span style={{ ...styles.velNum, color: '#2D7A52' }}>{summary?.closed_won || 0}</span>
          <span style={styles.velLabel}>Closed Won</span>
        </div>
      </div>

      {/* Kanban Board */}
      <div style={styles.kanban}>
        {COLUMNS.map(col => {
          const colOpps = opportunities.filter(o => o.status === col.key);
          const colSavings = colOpps.reduce((s, o) => s + (parseFloat(o.monthly_savings) || 0), 0);

          return (
            <div key={col.key} style={styles.column}>
              <div style={styles.colHeader}>
                <div style={styles.colHeaderLeft}>
                  <span style={{ ...styles.colDot, background: col.color }} />
                  <span style={styles.colTitle}>{col.label}</span>
                  <span style={styles.colCount}>{colOpps.length}</span>
                </div>
                {colSavings > 0 && (
                  <span style={styles.colSavings}>{formatCurrency(colSavings)}/mo</span>
                )}
              </div>
              <div style={styles.colBody}>
                {colOpps.length === 0 ? (
                  <div style={styles.colEmpty}>
                    <span style={styles.colEmptyText}>No items</span>
                  </div>
                ) : (
                  colOpps.map(opp => (
                    <KanbanCard key={opp.id} opp={opp} columnColor={col.color} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function KanbanCard({ opp, columnColor }) {
  return (
    <div style={styles.card}>
      <div style={styles.cardTop}>
        <span style={styles.cardLoan}>Loan #{opp.loan_id}</span>
        <span style={styles.cardProduct}>{PRODUCTS[opp.product] || opp.product}</span>
      </div>

      <div style={styles.cardRates}>
        <div style={styles.cardRate}>
          <span style={styles.cardRateLabel}>Current</span>
          <span style={styles.cardRateVal}>{formatRate(opp.current_rate)}</span>
        </div>
        <span style={styles.cardArrow}>→</span>
        <div style={styles.cardRate}>
          <span style={styles.cardRateLabel}>Available</span>
          <span style={{ ...styles.cardRateVal, color: '#2D7A52' }}>{formatRate(opp.perennia_rate)}</span>
        </div>
      </div>

      <div style={styles.cardBottom}>
        <span style={styles.cardSavings}>{formatCurrency(opp.monthly_savings)}/mo</span>
        {opp.estimated_break_even_months && (
          <span style={styles.cardBE}>{opp.estimated_break_even_months}mo BE</span>
        )}
      </div>

      {opp.status === 'detected' && (
        <button style={{ ...styles.cardAction, background: columnColor }}>
          Trigger Outreach
        </button>
      )}
    </div>
  );
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
    padding: '24px 32px',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
  },
  skeleton: { height: 600, borderRadius: 12, background: '#F2EDE2' },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  headerLeft: {},
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 26,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
  },
  subtitle: { fontSize: 13, color: '#8B8A7E', marginTop: 2 },
  headerRates: { display: 'flex', gap: 16 },
  headerRate: { fontSize: 12, color: '#4F554E', fontFamily: "'Geist Mono', monospace" },
  velocity: {
    display: 'flex',
    alignItems: 'center',
    gap: 24,
    padding: '14px 20px',
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    marginBottom: 20,
  },
  velItem: { display: 'flex', flexDirection: 'column' },
  velNum: { fontSize: 20, fontWeight: 700, color: '#1A1F1B', fontFamily: "'Fraunces', serif" },
  velLabel: { fontSize: 10, color: '#8B8A7E' },
  velDivider: { width: 1, height: 32, background: '#ECE6D8' },
  kanban: {
    display: 'grid',
    gridTemplateColumns: `repeat(${COLUMNS.length}, 1fr)`,
    gap: 12,
    alignItems: 'flex-start',
  },
  column: {
    background: '#F6F2EA',
    borderRadius: 10,
    overflow: 'hidden',
    minHeight: 400,
  },
  colHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 14px',
    borderBottom: '1px solid #ECE6D8',
  },
  colHeaderLeft: { display: 'flex', alignItems: 'center', gap: 8 },
  colDot: { width: 8, height: 8, borderRadius: '50%' },
  colTitle: { fontSize: 12, fontWeight: 600, color: '#1A1F1B' },
  colCount: { fontSize: 10, background: '#FFFFFF', padding: '1px 6px', borderRadius: 9999, color: '#4F554E' },
  colSavings: { fontSize: 10, color: '#B8924A', fontWeight: 600 },
  colBody: { padding: 10 },
  colEmpty: { padding: 20, textAlign: 'center' },
  colEmptyText: { fontSize: 11, color: '#B5B2A4' },
  card: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  },
  cardTop: { display: 'flex', justifyContent: 'space-between', marginBottom: 8 },
  cardLoan: { fontSize: 12, fontWeight: 600, color: '#1A1F1B' },
  cardProduct: { fontSize: 10, color: '#8B8A7E' },
  cardRates: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 },
  cardRate: { display: 'flex', flexDirection: 'column' },
  cardRateLabel: { fontSize: 8, color: '#B5B2A4', textTransform: 'uppercase' },
  cardRateVal: { fontSize: 13, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  cardArrow: { fontSize: 12, color: '#B5B2A4' },
  cardBottom: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  cardSavings: { fontSize: 12, fontWeight: 700, color: '#B8924A' },
  cardBE: { fontSize: 10, color: '#8B8A7E' },
  cardAction: {
    width: '100%',
    marginTop: 8,
    padding: '6px 12px',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 6,
    fontSize: 10,
    fontWeight: 600,
    cursor: 'pointer',
  },
};
