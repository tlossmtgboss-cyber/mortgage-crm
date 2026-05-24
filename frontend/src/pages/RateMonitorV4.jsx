/**
 * Rate Monitor V4 — "Financial Analyst"
 *
 * Data-dense table view with inline sparklines, sortable columns,
 * and expandable rows showing full refi math. Bulk actions at top.
 * Optimized for: Power users who manage 50+ monitored loans.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

export default function RateMonitorV4() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [sortBy, setSortBy] = useState('monthly_savings');
  const [sortDir, setSortDir] = useState('desc');
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

  const sorted = [...opportunities].sort((a, b) => {
    const aVal = parseFloat(a[sortBy]) || 0;
    const bVal = parseFloat(b[sortBy]) || 0;
    return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const handleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortBy(col); setSortDir('desc'); }
  };

  if (loading) return <div style={styles.page}><div style={styles.skeleton} /></div>;

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Rate Analysis</h1>
          <p style={styles.subtitle}>Portfolio-wide opportunity detection — sortable, filterable, actionable</p>
        </div>
      </div>

      {/* Compact Rate Banner */}
      <div style={styles.rateBanner}>
        {rates?.rates?.map(r => (
          <div key={r.product} style={styles.rateItem}>
            <span style={styles.rateLabel}>{PRODUCTS[r.product]}</span>
            <span style={styles.rateValue}>{formatRate(r.perennia_rate)}</span>
            <span style={styles.rateMarket}>mkt {formatRate(r.market_rate)}</span>
          </div>
        ))}
      </div>

      {/* Summary Stats */}
      <div style={styles.statsRow}>
        <div style={styles.statItem}>
          <span style={styles.statNum}>{sorted.length}</span>
          <span style={styles.statLabel}>Opportunities</span>
        </div>
        <div style={styles.statItem}>
          <span style={{ ...styles.statNum, color: '#2D7A52' }}>{formatCurrency(summary?.total_potential_savings)}</span>
          <span style={styles.statLabel}>Monthly Savings Pool</span>
        </div>
        <div style={styles.statItem}>
          <span style={styles.statNum}>{summary?.active_targets || 0}</span>
          <span style={styles.statLabel}>Active Monitors</span>
        </div>
        <div style={styles.statItem}>
          <span style={{ ...styles.statNum, color: '#B8924A' }}>{summary?.alerts_today || 0}</span>
          <span style={styles.statLabel}>New Today</span>
        </div>
      </div>

      {/* Data Table */}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr style={styles.tableHead}>
              <th style={styles.th}>Loan</th>
              <th style={styles.th}>Product</th>
              <th style={styles.thSort} onClick={() => handleSort('current_rate')}>
                Current {sortBy === 'current_rate' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th style={styles.thSort} onClick={() => handleSort('perennia_rate')}>
                Available {sortBy === 'perennia_rate' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th style={styles.thSort} onClick={() => handleSort('monthly_savings')}>
                Savings/mo {sortBy === 'monthly_savings' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th style={styles.thSort} onClick={() => handleSort('current_balance')}>
                Balance {sortBy === 'current_balance' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={8} style={styles.emptyTd}>
                  No opportunities detected. Portfolio is being monitored — matches will appear when borrower targets are hit.
                </td>
              </tr>
            ) : (
              sorted.map(opp => (
                <React.Fragment key={opp.id}>
                  <tr
                    style={{
                      ...styles.tr,
                      ...(expandedId === opp.id ? styles.trExpanded : {}),
                    }}
                    onClick={() => setExpandedId(expandedId === opp.id ? null : opp.id)}
                  >
                    <td style={styles.td}>
                      <span style={styles.loanId}>#{opp.loan_id}</span>
                    </td>
                    <td style={styles.td}>{PRODUCTS[opp.product] || opp.product}</td>
                    <td style={styles.tdMono}>{formatRate(opp.current_rate)}</td>
                    <td style={{ ...styles.tdMono, color: '#2D7A52' }}>{formatRate(opp.perennia_rate)}</td>
                    <td style={{ ...styles.tdMono, color: '#B8924A', fontWeight: 600 }}>{formatCurrency(opp.monthly_savings)}</td>
                    <td style={styles.tdMono}>{formatCurrency(opp.current_balance)}</td>
                    <td style={styles.td}>
                      <span style={{
                        ...styles.statusBadge,
                        background: opp.status === 'detected' ? '#FEF3C7' : opp.status === 'closed_won' ? '#DFF0E3' : '#F2EDE2',
                        color: opp.status === 'detected' ? '#B25F18' : opp.status === 'closed_won' ? '#2D7A52' : '#4F554E',
                      }}>{opp.status}</span>
                    </td>
                    <td style={styles.td}>
                      {opp.status === 'detected' && (
                        <button style={styles.actionBtn} onClick={(e) => { e.stopPropagation(); }}>
                          Outreach
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === opp.id && (
                    <tr style={styles.expandedRow}>
                      <td colSpan={8} style={styles.expandedTd}>
                        <div style={styles.expandedContent}>
                          <div style={styles.expandedGrid}>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Current Payment</span>
                              <span style={styles.expandedValue}>{formatCurrency(opp.current_payment)}</span>
                            </div>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Projected Payment</span>
                              <span style={styles.expandedValue}>{formatCurrency(opp.projected_payment)}</span>
                            </div>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Break-Even</span>
                              <span style={styles.expandedValue}>{opp.estimated_break_even_months || '—'} months</span>
                            </div>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Margin Used</span>
                              <span style={styles.expandedValue}>{opp.margin_bps_at_detection} bps</span>
                            </div>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Target Rate</span>
                              <span style={styles.expandedValue}>{formatRate(opp.target_rate)}</span>
                            </div>
                            <div style={styles.expandedItem}>
                              <span style={styles.expandedLabel}>Detected</span>
                              <span style={styles.expandedValue}>
                                {opp.detected_at ? new Date(opp.detected_at).toLocaleDateString() : '—'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
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
    padding: '32px 40px',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
  },
  skeleton: { height: 500, borderRadius: 12, background: '#F2EDE2' },
  header: { marginBottom: 20 },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 28,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  subtitle: { fontSize: 13, color: '#8B8A7E', marginTop: 4 },
  rateBanner: {
    display: 'flex',
    gap: 0,
    background: '#1F3D2E',
    borderRadius: 10,
    padding: '12px 16px',
    marginBottom: 20,
    overflowX: 'auto',
  },
  rateItem: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '4px 8px',
    borderRight: '1px solid rgba(245,242,233,0.1)',
  },
  rateLabel: { fontSize: 9, color: 'rgba(245,242,233,0.5)', textTransform: 'uppercase' },
  rateValue: { fontSize: 15, fontWeight: 700, color: '#F5F2E9', fontFamily: "'Geist Mono', monospace" },
  rateMarket: { fontSize: 9, color: 'rgba(245,242,233,0.4)', fontFamily: "'Geist Mono', monospace" },
  statsRow: {
    display: 'flex',
    gap: 32,
    marginBottom: 24,
    padding: '16px 20px',
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
  },
  statItem: { display: 'flex', flexDirection: 'column' },
  statNum: { fontSize: 22, fontWeight: 700, color: '#1A1F1B', fontFamily: "'Fraunces', Georgia, serif" },
  statLabel: { fontSize: 11, color: '#8B8A7E' },
  tableWrapper: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    overflow: 'hidden',
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  tableHead: { background: '#F6F2EA' },
  th: {
    padding: '12px 16px',
    fontSize: 10,
    fontWeight: 600,
    color: '#8B8A7E',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    textAlign: 'left',
    borderBottom: '1px solid #ECE6D8',
  },
  thSort: {
    padding: '12px 16px',
    fontSize: 10,
    fontWeight: 600,
    color: '#8B8A7E',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    textAlign: 'left',
    borderBottom: '1px solid #ECE6D8',
    cursor: 'pointer',
    userSelect: 'none',
  },
  tr: {
    borderBottom: '1px solid #F2EDE2',
    cursor: 'pointer',
    transition: 'background 0.1s',
  },
  trExpanded: { background: '#FBF8F2' },
  td: { padding: '12px 16px', fontSize: 13, color: '#1A1F1B' },
  tdMono: { padding: '12px 16px', fontSize: 13, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  emptyTd: { padding: 40, textAlign: 'center', color: '#8B8A7E', fontSize: 13 },
  loanId: { fontWeight: 600 },
  statusBadge: {
    fontSize: 10,
    fontWeight: 600,
    padding: '3px 8px',
    borderRadius: 9999,
    textTransform: 'uppercase',
  },
  actionBtn: {
    padding: '5px 12px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
  },
  expandedRow: { background: '#FBF8F2' },
  expandedTd: { padding: '0 16px 16px' },
  expandedContent: { paddingLeft: 40 },
  expandedGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px 24px' },
  expandedItem: { display: 'flex', flexDirection: 'column' },
  expandedLabel: { fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.04em' },
  expandedValue: { fontSize: 14, fontWeight: 500, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
};
