/**
 * Rate Monitor V3 — "AI Action Feed"
 *
 * Timeline-style layout centered around AI actions and decisions.
 * Rates are a persistent top bar; the main content is a vertical feed
 * of "Aria detected → Aria reached out → borrower responded" events.
 * Optimized for: LOs who want to see the AI working in real-time.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

const STATUS_CONFIG = {
  detected: { label: 'Detected', color: '#B8924A', bg: '#FEF3C7', icon: '📡' },
  outreach_sent: { label: 'Outreach Sent', color: '#1F3D2E', bg: '#DFF0E3', icon: '📤' },
  borrower_responded: { label: 'Responded', color: '#2D7A52', bg: '#DFF0E3', icon: '💬' },
  meeting_booked: { label: 'Meeting Booked', color: '#1F3D2E', bg: '#E5EDE6', icon: '📅' },
  closed_won: { label: 'Closed Won', color: '#2D7A52', bg: '#DFF0E3', icon: '🏆' },
  closed_lost: { label: 'Lost', color: '#9B2C2C', bg: '#FDE8E8', icon: '✕' },
  expired: { label: 'Expired', color: '#8B8A7E', bg: '#F2EDE2', icon: '⏰' },
};

export default function RateMonitorV3() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes, oppsRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
        fetch(`${API_BASE}/opportunities?limit=50`, { credentials: 'include' }),
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

  const filtered = filter === 'all'
    ? opportunities
    : opportunities.filter(o => o.status === filter);

  if (loading) return <div style={styles.page}><div style={styles.skeleton} /></div>;

  return (
    <div style={styles.page}>
      {/* Persistent Rate Bar */}
      <div style={styles.rateBar}>
        <div style={styles.rateBarLeft}>
          <h1 style={styles.title}>Rate Intelligence</h1>
          {rates?.stale && <span style={styles.staleBadge}>STALE</span>}
        </div>
        <div style={styles.rateBarRates}>
          {rates?.rates?.map(r => (
            <div key={r.product} style={styles.rateBarItem}>
              <span style={styles.rateBarLabel}>{PRODUCTS[r.product]}</span>
              <span style={styles.rateBarValue}>{formatRate(r.perennia_rate)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Stats */}
      <div style={styles.quickStats}>
        <div style={styles.qStat}>
          <span style={styles.qStatNum}>{summary?.pending_opportunities || 0}</span>
          <span style={styles.qStatLabel}>Awaiting Action</span>
        </div>
        <div style={styles.qStatDivider} />
        <div style={styles.qStat}>
          <span style={{ ...styles.qStatNum, color: '#2D7A52' }}>{formatCurrency(summary?.total_potential_savings)}</span>
          <span style={styles.qStatLabel}>Total Savings Potential</span>
        </div>
        <div style={styles.qStatDivider} />
        <div style={styles.qStat}>
          <span style={styles.qStatNum}>{summary?.alerts_today || 0}</span>
          <span style={styles.qStatLabel}>New Today</span>
        </div>
        <div style={styles.qStatDivider} />
        <div style={styles.qStat}>
          <span style={{ ...styles.qStatNum, color: '#B8924A' }}>{summary?.closed_won || 0}</span>
          <span style={styles.qStatLabel}>Conversions</span>
        </div>
      </div>

      {/* Filter Pills */}
      <div style={styles.filterBar}>
        {['all', 'detected', 'outreach_sent', 'meeting_booked', 'closed_won'].map(f => (
          <button
            key={f}
            style={{
              ...styles.filterPill,
              ...(filter === f ? styles.filterPillActive : {}),
            }}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All' : STATUS_CONFIG[f]?.label || f}
            {f !== 'all' && <span style={styles.filterCount}>
              {opportunities.filter(o => o.status === f).length}
            </span>}
          </button>
        ))}
      </div>

      {/* Activity Feed */}
      <div style={styles.feed}>
        {filtered.length === 0 ? (
          <div style={styles.emptyFeed}>
            <div style={styles.emptyIcon}>📡</div>
            <h3 style={styles.emptyTitle}>Monitoring Active</h3>
            <p style={styles.emptyText}>Aria is watching {summary?.active_targets || 0} loan targets. When rates hit a borrower's threshold, action items will appear here.</p>
          </div>
        ) : (
          filtered.map(opp => (
            <FeedItem key={opp.id} opp={opp} />
          ))
        )}
      </div>
    </div>
  );
}

function FeedItem({ opp }) {
  const config = STATUS_CONFIG[opp.status] || STATUS_CONFIG.detected;

  return (
    <div style={styles.feedItem}>
      {/* Timeline Dot */}
      <div style={styles.timelineDot}>
        <div style={{ ...styles.dot, background: config.bg, borderColor: config.color }}>
          <span style={styles.dotIcon}>{config.icon}</span>
        </div>
        <div style={styles.timelineLine} />
      </div>

      {/* Content */}
      <div style={styles.feedContent}>
        <div style={styles.feedHeader}>
          <span style={styles.feedTime}>
            {opp.detected_at ? new Date(opp.detected_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
          </span>
          <span style={{ ...styles.feedStatus, background: config.bg, color: config.color }}>{config.label}</span>
        </div>

        <div style={styles.feedCard}>
          <div style={styles.feedCardTop}>
            <span style={styles.feedLoan}>Loan #{opp.loan_id}</span>
            <span style={styles.feedProduct}>{PRODUCTS[opp.product]}</span>
          </div>

          <div style={styles.feedRates}>
            <span style={styles.feedRateItem}>
              <span style={styles.feedRateLabel}>Was</span>
              <span style={styles.feedRateVal}>{formatRate(opp.current_rate)}</span>
            </span>
            <span style={styles.feedRateArrow}>→</span>
            <span style={styles.feedRateItem}>
              <span style={styles.feedRateLabel}>Now Available</span>
              <span style={{ ...styles.feedRateVal, color: '#2D7A52' }}>{formatRate(opp.perennia_rate)}</span>
            </span>
            <span style={styles.feedSavings}>{formatCurrency(opp.monthly_savings)}/mo saved</span>
          </div>

          {opp.status === 'detected' && (
            <div style={styles.feedActions}>
              <button style={styles.primaryBtn}>Let Aria Handle This</button>
              <button style={styles.ghostBtn}>Review First</button>
            </div>
          )}
        </div>
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
    padding: '0',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
  },
  skeleton: { height: 400, margin: 32, borderRadius: 12, background: '#F2EDE2' },
  rateBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 40px',
    background: '#FFFFFF',
    borderBottom: '1px solid #ECE6D8',
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  rateBarLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 22,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
  },
  staleBadge: { fontSize: 9, padding: '2px 6px', borderRadius: 4, background: '#FEF3C7', color: '#B25F18', fontWeight: 700 },
  rateBarRates: { display: 'flex', gap: 16 },
  rateBarItem: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' },
  rateBarLabel: { fontSize: 9, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.04em' },
  rateBarValue: { fontSize: 14, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  quickStats: {
    display: 'flex',
    alignItems: 'center',
    padding: '20px 40px',
    gap: 32,
  },
  qStat: { display: 'flex', flexDirection: 'column' },
  qStatNum: { fontSize: 24, fontWeight: 700, color: '#1A1F1B', fontFamily: "'Fraunces', Georgia, serif" },
  qStatLabel: { fontSize: 11, color: '#8B8A7E', marginTop: 2 },
  qStatDivider: { width: 1, height: 36, background: '#ECE6D8' },
  filterBar: {
    display: 'flex',
    gap: 8,
    padding: '0 40px 20px',
  },
  filterPill: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 14px',
    borderRadius: 9999,
    border: '1px solid #ECE6D8',
    background: '#FFFFFF',
    color: '#4F554E',
    fontSize: 12,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  filterPillActive: {
    background: '#1F3D2E',
    color: '#F5F2E9',
    borderColor: '#1F3D2E',
  },
  filterCount: {
    fontSize: 10,
    background: 'rgba(0,0,0,0.1)',
    padding: '1px 6px',
    borderRadius: 9999,
  },
  feed: {
    padding: '0 40px 40px',
    maxWidth: 800,
  },
  emptyFeed: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 48,
    textAlign: 'center',
  },
  emptyIcon: { fontSize: 40, marginBottom: 16 },
  emptyTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 18, color: '#1A1F1B', margin: '0 0 8px' },
  emptyText: { fontSize: 13, color: '#8B8A7E', maxWidth: 400, margin: '0 auto' },
  feedItem: {
    display: 'flex',
    gap: 16,
    marginBottom: 0,
  },
  timelineDot: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    width: 40,
  },
  dot: {
    width: 36,
    height: 36,
    borderRadius: '50%',
    border: '2px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotIcon: { fontSize: 16 },
  timelineLine: { width: 2, flex: 1, background: '#ECE6D8', minHeight: 20 },
  feedContent: { flex: 1, paddingBottom: 24 },
  feedHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  feedTime: { fontSize: 11, color: '#8B8A7E' },
  feedStatus: { fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 9999 },
  feedCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    padding: 16,
  },
  feedCardTop: { display: 'flex', justifyContent: 'space-between', marginBottom: 12 },
  feedLoan: { fontSize: 14, fontWeight: 600, color: '#1A1F1B' },
  feedProduct: { fontSize: 12, color: '#8B8A7E' },
  feedRates: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' },
  feedRateItem: { display: 'flex', flexDirection: 'column' },
  feedRateLabel: { fontSize: 9, color: '#8B8A7E', textTransform: 'uppercase' },
  feedRateVal: { fontSize: 16, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  feedRateArrow: { fontSize: 16, color: '#B5B2A4' },
  feedSavings: { fontSize: 13, fontWeight: 600, color: '#B8924A', marginLeft: 'auto' },
  feedActions: { display: 'flex', gap: 10, paddingTop: 12, borderTop: '1px solid #F2EDE2' },
  primaryBtn: {
    padding: '8px 16px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
  },
  ghostBtn: {
    padding: '8px 16px',
    background: 'transparent',
    color: '#1F3D2E',
    border: '1px solid #ECE6D8',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 500,
    cursor: 'pointer',
  },
};
