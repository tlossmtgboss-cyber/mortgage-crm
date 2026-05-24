/**
 * Rate Monitor V8 — "Executive Summary"
 *
 * Clean, minimal, high-level overview designed for managers/executives.
 * Large numbers, trend indicators, and a "what Aria did this week" digest.
 * No raw data tables — just outcomes, ROI, and portfolio health.
 * Optimized for: Executives and branch managers who want the 30-second picture.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

export default function RateMonitorV8() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
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
      console.error('Fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 120000); // 2min for exec view
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div style={styles.page}><div style={styles.skeleton} /></div>;

  const annualSavings = (parseFloat(summary?.total_potential_savings) || 0) * 12;
  const conversionRate = summary?.closed_won && summary?.pending_opportunities
    ? Math.round((summary.closed_won / (summary.closed_won + summary.pending_opportunities + (summary.outreach_sent || 0))) * 100)
    : 0;

  const topOpps = opportunities
    .filter(o => o.status === 'detected')
    .sort((a, b) => (parseFloat(b.monthly_savings) || 0) - (parseFloat(a.monthly_savings) || 0))
    .slice(0, 5);

  return (
    <div style={styles.page}>
      {/* Headline */}
      <div style={styles.header}>
        <h1 style={styles.title}>Rate Intelligence</h1>
        <span style={styles.dateLabel}>
          {new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}
        </span>
      </div>

      {/* Key Metrics — Large */}
      <div style={styles.heroGrid}>
        <div style={styles.heroCard}>
          <span style={styles.heroLabel}>Monthly Savings Potential</span>
          <span style={styles.heroValue}>{formatCurrency(summary?.total_potential_savings)}</span>
          <span style={styles.heroSub}>across {summary?.pending_opportunities || 0} active opportunities</span>
        </div>
        <div style={styles.heroCard}>
          <span style={styles.heroLabel}>Annual Revenue Opportunity</span>
          <span style={{ ...styles.heroValue, color: '#B8924A' }}>{formatCurrency(annualSavings)}</span>
          <span style={styles.heroSub}>if all opportunities convert</span>
        </div>
        <div style={styles.heroCard}>
          <span style={styles.heroLabel}>Conversion Rate</span>
          <span style={{ ...styles.heroValue, color: '#2D7A52' }}>{conversionRate}%</span>
          <span style={styles.heroSub}>{summary?.closed_won || 0} won of total pipeline</span>
        </div>
      </div>

      {/* Rate Snapshot */}
      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Today's Market</h2>
        <div style={styles.rateRow}>
          {rates?.rates?.map(r => (
            <div key={r.product} style={styles.rateItem}>
              <span style={styles.rateItemLabel}>{PRODUCTS[r.product]}</span>
              <span style={styles.rateItemValue}>{formatRate(r.perennia_rate)}</span>
              <span style={styles.rateItemMarket}>market {formatRate(r.market_rate)}</span>
            </div>
          ))}
        </div>
        {rates?.stale && (
          <p style={styles.staleNote}>Note: Rate data is over 24 hours old. FRED updates on business days.</p>
        )}
      </div>

      {/* This Week's Activity */}
      <div style={styles.columns}>
        {/* Pipeline Summary */}
        <div style={styles.colCard}>
          <h2 style={styles.sectionTitle}>Pipeline Status</h2>
          <div style={styles.pipelineList}>
            <PipelineRow label="Targets Being Monitored" value={summary?.active_targets || 0} />
            <PipelineRow label="New Alerts (today)" value={summary?.alerts_today || 0} highlight={summary?.alerts_today > 0} />
            <PipelineRow label="New Alerts (this week)" value={summary?.alerts_this_week || 0} />
            <PipelineRow label="Awaiting Outreach" value={summary?.pending_opportunities || 0} color="#B8924A" />
            <PipelineRow label="Outreach Sent" value={summary?.outreach_sent || 0} />
            <PipelineRow label="Meetings Booked" value={summary?.meetings_booked || 0} color="#2D7A52" />
            <PipelineRow label="Deals Closed" value={summary?.closed_won || 0} color="#1F3D2E" />
          </div>
        </div>

        {/* Highest Value Opportunities */}
        <div style={styles.colCard}>
          <h2 style={styles.sectionTitle}>Top Opportunities</h2>
          {topOpps.length === 0 ? (
            <p style={styles.emptyText}>No pending opportunities. All targets are being monitored.</p>
          ) : (
            <div style={styles.topList}>
              {topOpps.map((opp, i) => (
                <div key={opp.id} style={styles.topItem}>
                  <div style={styles.topRank}>
                    <span style={styles.topRankNum}>{i + 1}</span>
                  </div>
                  <div style={styles.topContent}>
                    <div style={styles.topRow}>
                      <span style={styles.topLoan}>Loan #{opp.loan_id}</span>
                      <span style={styles.topSavings}>{formatCurrency(opp.monthly_savings)}/mo</span>
                    </div>
                    <div style={styles.topRow}>
                      <span style={styles.topProduct}>{PRODUCTS[opp.product]}</span>
                      <span style={styles.topRates}>{formatRate(opp.current_rate)} → {formatRate(opp.perennia_rate)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Aria Digest */}
      <div style={styles.digestCard}>
        <div style={styles.digestHeader}>
          <div style={styles.digestAvatar}>A</div>
          <div>
            <h3 style={styles.digestTitle}>Aria's Weekly Digest</h3>
            <p style={styles.digestSub}>Automated intelligence summary</p>
          </div>
        </div>
        <div style={styles.digestBody}>
          <p style={styles.digestText}>
            This week, I monitored <strong>{summary?.active_targets || 0} loan targets</strong> and
            detected <strong>{summary?.alerts_this_week || 0} new opportunities</strong>.
            {summary?.outreach_sent > 0 && (
              <> I sent outreach to <strong>{summary.outreach_sent}</strong> borrowers. </>
            )}
            {summary?.meetings_booked > 0 && (
              <> <strong>{summary.meetings_booked}</strong> meetings were booked. </>
            )}
            {summary?.closed_won > 0 && (
              <> <strong>{summary.closed_won}</strong> deals closed. </>
            )}
            {(summary?.alerts_this_week || 0) === 0 && (
              <> Market rates haven't hit any borrower targets this week — portfolio is stable. </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

function PipelineRow({ label, value, color, highlight }) {
  return (
    <div style={{
      ...styles.pipeRow,
      ...(highlight ? { background: '#FEF3C7' } : {}),
    }}>
      <span style={styles.pipeLabel}>{label}</span>
      <span style={{
        ...styles.pipeValue,
        ...(color ? { color } : {}),
      }}>{value}</span>
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
    padding: '40px 48px',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
    maxWidth: 1100,
    margin: '0 auto',
  },
  skeleton: { height: 500, borderRadius: 14, background: '#F2EDE2' },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 32,
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 32,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  dateLabel: { fontSize: 13, color: '#8B8A7E' },
  heroGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 16,
    marginBottom: 32,
  },
  heroCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 14,
    padding: '28px 24px',
    display: 'flex',
    flexDirection: 'column',
  },
  heroLabel: { fontSize: 11, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 },
  heroValue: {
    fontSize: 36,
    fontWeight: 700,
    color: '#1A1F1B',
    fontFamily: "'Fraunces', Georgia, serif",
    letterSpacing: '-0.02em',
  },
  heroSub: { fontSize: 12, color: '#B5B2A4', marginTop: 4 },
  section: { marginBottom: 32 },
  sectionTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 18,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: '0 0 16px',
  },
  rateRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: 12,
  },
  rateItem: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    padding: '14px 16px',
    textAlign: 'center',
  },
  rateItemLabel: { display: 'block', fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase', marginBottom: 4 },
  rateItemValue: { display: 'block', fontSize: 20, fontWeight: 700, color: '#1F3D2E', fontFamily: "'Geist Mono', monospace" },
  rateItemMarket: { display: 'block', fontSize: 10, color: '#B5B2A4', fontFamily: "'Geist Mono', monospace", marginTop: 2 },
  staleNote: { fontSize: 11, color: '#B25F18', marginTop: 8 },
  columns: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 20,
    marginBottom: 32,
  },
  colCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 24,
  },
  pipelineList: {},
  pipeRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderRadius: 6,
    marginBottom: 2,
  },
  pipeLabel: { fontSize: 13, color: '#4F554E' },
  pipeValue: { fontSize: 14, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  emptyText: { fontSize: 13, color: '#8B8A7E' },
  topList: {},
  topItem: {
    display: 'flex',
    gap: 12,
    padding: '10px 0',
    borderBottom: '1px solid #F2EDE2',
  },
  topRank: {
    width: 28,
    height: 28,
    borderRadius: '50%',
    background: '#F6F2EA',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  topRankNum: { fontSize: 12, fontWeight: 700, color: '#4F554E' },
  topContent: { flex: 1 },
  topRow: { display: 'flex', justifyContent: 'space-between', marginBottom: 2 },
  topLoan: { fontSize: 13, fontWeight: 600, color: '#1A1F1B' },
  topSavings: { fontSize: 13, fontWeight: 700, color: '#B8924A' },
  topProduct: { fontSize: 11, color: '#8B8A7E' },
  topRates: { fontSize: 11, color: '#4F554E', fontFamily: "'Geist Mono', monospace" },
  digestCard: {
    background: 'linear-gradient(160deg, #E5EDE6 0%, #FFFFFF 50%, #FBF8F2 100%)',
    border: '1px solid #D8E8DC',
    borderRadius: 14,
    padding: 28,
  },
  digestHeader: { display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 },
  digestAvatar: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: '#1F3D2E',
    color: '#F5F2E9',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 18,
    fontWeight: 700,
    fontFamily: "'Fraunces', serif",
  },
  digestTitle: { fontFamily: "'Fraunces', serif", fontSize: 16, fontWeight: 600, color: '#1A1F1B', margin: 0 },
  digestSub: { fontSize: 11, color: '#8B8A7E', margin: 0 },
  digestBody: {},
  digestText: { fontSize: 14, color: '#1A1F1B', lineHeight: 1.6, margin: 0 },
};
