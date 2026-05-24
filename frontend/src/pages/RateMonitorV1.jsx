/**
 * Rate Monitor V1 — "Command Center"
 *
 * Full-width dashboard with real-time rate ticker at top,
 * 4-column stat grid, AI action feed, and opportunity cards.
 * Optimized for: LOs who want instant visibility + one-click AI actions.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';

const API_BASE = '/api/rate-watch';

const PRODUCTS = {
  '30_fixed': '30 Yr Fixed',
  '15_fixed': '15 Yr Fixed',
  '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 SOFR ARM',
  '30_fha': '30 Yr FHA',
  '30_va': '30 Yr VA',
};

export default function RateMonitorV1() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes, oppsRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
        fetch(`${API_BASE}/opportunities?limit=20`, { credentials: 'include' }),
      ]);
      if (ratesRes.ok) setRates(await ratesRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
      if (oppsRes.ok) setOpportunities(await oppsRes.json());
    } catch (e) {
      console.error('Rate watch fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <PageSkeleton />;

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Rate Command Center</h1>
          <p style={styles.subtitle}>Real-time market monitoring with AI-powered refi detection</p>
        </div>
        <div style={styles.headerActions}>
          <span style={styles.liveBadge}>
            <span style={styles.liveDot} />
            LIVE
          </span>
          {rates?.stale && <span style={styles.staleBadge}>STALE DATA</span>}
        </div>
      </div>

      {/* Rate Ticker Strip */}
      <div style={styles.tickerStrip}>
        {rates?.rates?.map(r => (
          <div key={r.product} style={styles.tickerItem}>
            <span style={styles.tickerLabel}>{PRODUCTS[r.product] || r.product}</span>
            <span style={styles.tickerRate}>{formatRate(r.perennia_rate)}</span>
            <span style={styles.tickerMarket}>{formatRate(r.market_rate)}</span>
          </div>
        ))}
      </div>

      {/* Stats Grid */}
      <div style={styles.statsGrid}>
        <StatCard label="Active Monitors" value={summary?.active_targets || 0} icon="📡" />
        <StatCard label="Alerts Today" value={summary?.alerts_today || 0} icon="🔔" highlight={summary?.alerts_today > 0} />
        <StatCard label="Pending Opportunities" value={summary?.pending_opportunities || 0} icon="💰" highlight />
        <StatCard label="Monthly Savings Potential" value={formatCurrency(summary?.total_potential_savings)} icon="📈" />
        <StatCard label="Outreach Sent" value={summary?.outreach_sent || 0} icon="📤" />
        <StatCard label="Meetings Booked" value={summary?.meetings_booked || 0} icon="📅" />
        <StatCard label="Closed Won" value={summary?.closed_won || 0} icon="🏆" accent />
        <StatCard label="This Week" value={summary?.alerts_this_week || 0} icon="📊" />
      </div>

      {/* Opportunities Feed */}
      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>AI-Detected Opportunities</h2>
        <p style={styles.sectionSubtitle}>Borrowers whose target rate has been hit — ready for outreach</p>

        {opportunities.length === 0 ? (
          <div style={styles.emptyState}>
            <p style={styles.emptyText}>No active opportunities yet. As rates move and hit borrower targets, Aria will surface matches here.</p>
          </div>
        ) : (
          <div style={styles.oppGrid}>
            {opportunities.map(opp => (
              <OpportunityCard key={opp.id} opp={opp} onAction={fetchData} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, icon, highlight, accent }) {
  return (
    <div style={{
      ...styles.statCard,
      ...(highlight ? styles.statHighlight : {}),
      ...(accent ? styles.statAccent : {}),
    }}>
      <div style={styles.statIcon}>{icon}</div>
      <div style={styles.statValue}>{value}</div>
      <div style={styles.statLabel}>{label}</div>
    </div>
  );
}

function OpportunityCard({ opp, onAction }) {
  const handleTriggerOutreach = async () => {
    toast.info('Aria is preparing personalized outreach...');
  };

  return (
    <div style={styles.oppCard}>
      <div style={styles.oppHeader}>
        <span style={styles.oppProduct}>{PRODUCTS[opp.product] || opp.product}</span>
        <span style={{
          ...styles.oppStatus,
          background: opp.status === 'detected' ? '#DFF0E3' : '#FEF3C7',
          color: opp.status === 'detected' ? '#2D7A52' : '#B25F18',
        }}>{opp.status}</span>
      </div>
      <div style={styles.oppMetrics}>
        <div style={styles.oppMetric}>
          <span style={styles.oppMetricLabel}>Current Rate</span>
          <span style={styles.oppMetricValue}>{formatRate(opp.current_rate)}</span>
        </div>
        <div style={styles.oppMetric}>
          <span style={styles.oppMetricLabel}>Perennia Rate</span>
          <span style={{ ...styles.oppMetricValue, color: '#2D7A52' }}>{formatRate(opp.perennia_rate)}</span>
        </div>
        <div style={styles.oppMetric}>
          <span style={styles.oppMetricLabel}>Monthly Savings</span>
          <span style={{ ...styles.oppMetricValue, color: '#B8924A' }}>{formatCurrency(opp.monthly_savings)}</span>
        </div>
      </div>
      {opp.estimated_break_even_months && (
        <div style={styles.oppBreakEven}>Break-even: {opp.estimated_break_even_months} months</div>
      )}
      {opp.status === 'detected' && (
        <button style={styles.oppAction} onClick={handleTriggerOutreach}>
          Let Aria Reach Out
        </button>
      )}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div style={styles.page}>
      <div style={{ height: 60, borderRadius: 10, background: '#F2EDE2', marginBottom: 24 }} />
      <div style={{ height: 80, borderRadius: 10, background: '#F2EDE2', marginBottom: 24 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {[...Array(8)].map((_, i) => (
          <div key={i} style={{ height: 100, borderRadius: 10, background: '#F2EDE2' }} />
        ))}
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
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 24,
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 32,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: 14,
    color: '#8B8A7E',
    marginTop: 4,
  },
  headerActions: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  liveBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 12px',
    borderRadius: 9999,
    background: '#DFF0E3',
    color: '#2D7A52',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.05em',
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#2D7A52',
    animation: 'pulse 2s infinite',
  },
  staleBadge: {
    padding: '4px 12px',
    borderRadius: 9999,
    background: '#FEF3C7',
    color: '#B25F18',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.05em',
  },
  tickerStrip: {
    display: 'flex',
    gap: 2,
    padding: '16px 20px',
    background: '#1F3D2E',
    borderRadius: 12,
    marginBottom: 24,
    overflowX: 'auto',
  },
  tickerItem: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '8px 12px',
    minWidth: 120,
  },
  tickerLabel: {
    fontSize: 10,
    color: 'rgba(245, 242, 233, 0.6)',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    marginBottom: 4,
  },
  tickerRate: {
    fontSize: 20,
    fontWeight: 700,
    color: '#F5F2E9',
    fontFamily: "'Geist Mono', monospace",
  },
  tickerMarket: {
    fontSize: 11,
    color: 'rgba(245, 242, 233, 0.5)',
    fontFamily: "'Geist Mono', monospace",
    marginTop: 2,
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: 16,
    marginBottom: 32,
  },
  statCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: '20px 16px',
    textAlign: 'center',
    transition: 'box-shadow 0.2s',
  },
  statHighlight: {
    borderColor: '#B8924A',
    background: 'linear-gradient(160deg, #F5EDD9 0%, #FFFFFF 50%)',
  },
  statAccent: {
    borderColor: '#2D7A52',
    background: 'linear-gradient(160deg, #DFF0E3 0%, #FFFFFF 50%)',
  },
  statIcon: { fontSize: 24, marginBottom: 8 },
  statValue: {
    fontSize: 28,
    fontWeight: 700,
    color: '#1A1F1B',
    fontFamily: "'Fraunces', Georgia, serif",
  },
  statLabel: {
    fontSize: 11,
    color: '#8B8A7E',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    marginTop: 4,
  },
  section: { marginBottom: 32 },
  sectionTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 22,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: '0 0 4px 0',
  },
  sectionSubtitle: {
    fontSize: 13,
    color: '#8B8A7E',
    marginBottom: 16,
  },
  emptyState: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 40,
    textAlign: 'center',
  },
  emptyText: { color: '#8B8A7E', fontSize: 14 },
  oppGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: 16,
  },
  oppCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 20,
    transition: 'box-shadow 0.2s',
  },
  oppHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  oppProduct: {
    fontSize: 14,
    fontWeight: 600,
    color: '#1A1F1B',
  },
  oppStatus: {
    fontSize: 10,
    fontWeight: 700,
    padding: '3px 8px',
    borderRadius: 9999,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  oppMetrics: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: 12,
    marginBottom: 12,
  },
  oppMetric: { display: 'flex', flexDirection: 'column' },
  oppMetricLabel: { fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.04em' },
  oppMetricValue: { fontSize: 16, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  oppBreakEven: { fontSize: 12, color: '#4F554E', marginBottom: 12 },
  oppAction: {
    width: '100%',
    padding: '10px 16px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
};
