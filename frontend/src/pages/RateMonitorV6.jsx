/**
 * Rate Monitor V6 — "Market Dashboard"
 *
 * Rate-centric view with large rate cards as primary, history chart placeholder,
 * margin controls, and source health indicators. Best for LOs/admins who
 * care about the rate data itself and want to tune margins.
 * Optimized for: Rate-savvy users and admins managing margin configuration.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

export default function RateMonitorV6() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedProduct, setSelectedProduct] = useState('30_fixed');

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
      ]);
      if (ratesRes.ok) setRates(await ratesRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
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

  const selectedRate = rates?.rates?.find(r => r.product === selectedProduct);

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Market Rates</h1>
          <p style={styles.subtitle}>
            Last updated: {rates?.fetched_at ? new Date(rates.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
            {rates?.stale && <span style={styles.staleInline}> — Data is stale (24h+)</span>}
          </p>
        </div>
        <div style={styles.sourceStatus}>
          <div style={styles.sourceItem}>
            <span style={{ ...styles.sourceDot, background: rates?.stale ? '#B25F18' : '#2D7A52' }} />
            <span style={styles.sourceLabel}>FRED API</span>
          </div>
        </div>
      </div>

      {/* Rate Cards Grid */}
      <div style={styles.rateGrid}>
        {rates?.rates?.map(r => (
          <div
            key={r.product}
            style={{
              ...styles.rateCard,
              ...(selectedProduct === r.product ? styles.rateCardSelected : {}),
            }}
            onClick={() => setSelectedProduct(r.product)}
          >
            <div style={styles.rateCardHeader}>
              <span style={styles.rateCardLabel}>{PRODUCTS[r.product]}</span>
              <span style={styles.rateCardMargin}>{r.margin_bps} bps</span>
            </div>
            <div style={styles.rateCardBody}>
              <div style={styles.rateCardPerennia}>
                <span style={styles.rateCardPLabel}>Your Rate</span>
                <span style={styles.rateCardPValue}>{formatRate(r.perennia_rate)}</span>
              </div>
              <div style={styles.rateCardMarket}>
                <span style={styles.rateCardMLabel}>Market</span>
                <span style={styles.rateCardMValue}>{formatRate(r.market_rate)}</span>
              </div>
            </div>
            <div style={styles.rateCardFooter}>
              <span style={styles.rateCardSource}>{r.source}</span>
              <span style={styles.rateCardTime}>
                {r.observed_at ? new Date(r.observed_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '—'}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Selected Product Detail */}
      {selectedRate && (
        <div style={styles.detailSection}>
          <div style={styles.detailHeader}>
            <h2 style={styles.detailTitle}>{PRODUCTS[selectedProduct]} Detail</h2>
          </div>

          <div style={styles.detailGrid}>
            {/* Rate Breakdown */}
            <div style={styles.detailCard}>
              <h3 style={styles.detailCardTitle}>Rate Breakdown</h3>
              <div style={styles.breakdownRow}>
                <span style={styles.breakdownLabel}>Market Rate (Source)</span>
                <span style={styles.breakdownValue}>{formatRate(selectedRate.market_rate)}</span>
              </div>
              <div style={styles.breakdownRow}>
                <span style={styles.breakdownLabel}>Margin Applied</span>
                <span style={styles.breakdownValue}>-{selectedRate.margin_bps} bps ({(selectedRate.margin_bps / 100).toFixed(2)}%)</span>
              </div>
              <div style={styles.breakdownDivider} />
              <div style={styles.breakdownRow}>
                <span style={{ ...styles.breakdownLabel, fontWeight: 600 }}>Perennia Rate</span>
                <span style={{ ...styles.breakdownValue, color: '#2D7A52', fontWeight: 700, fontSize: 20 }}>{formatRate(selectedRate.perennia_rate)}</span>
              </div>
              <div style={styles.breakdownRow}>
                <span style={styles.breakdownLabel}>Points</span>
                <span style={styles.breakdownValue}>{selectedRate.points || '0.000'}</span>
              </div>
            </div>

            {/* Chart Placeholder */}
            <div style={styles.detailCard}>
              <h3 style={styles.detailCardTitle}>30-Day Trend</h3>
              <div style={styles.chartPlaceholder}>
                <div style={styles.chartLine} />
                <p style={styles.chartText}>Rate history chart — coming soon</p>
              </div>
            </div>

            {/* Margin Config */}
            <div style={styles.detailCard}>
              <h3 style={styles.detailCardTitle}>Margin Configuration</h3>
              <div style={styles.marginConfig}>
                <div style={styles.marginRow}>
                  <span style={styles.marginLabel}>Global Margin</span>
                  <span style={styles.marginValue}>{selectedRate.margin_bps} bps</span>
                </div>
                <p style={styles.marginNote}>
                  Perennia rate = market rate − margin. Lower margin = more competitive rate for borrowers.
                  Admin can adjust via Settings.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Portfolio Impact */}
      <div style={styles.impactSection}>
        <h2 style={styles.detailTitle}>Portfolio Impact</h2>
        <div style={styles.impactGrid}>
          <div style={styles.impactCard}>
            <span style={styles.impactNum}>{summary?.active_targets || 0}</span>
            <span style={styles.impactLabel}>Loans Being Monitored</span>
          </div>
          <div style={styles.impactCard}>
            <span style={{ ...styles.impactNum, color: '#B8924A' }}>{summary?.pending_opportunities || 0}</span>
            <span style={styles.impactLabel}>Rate Triggers Hit</span>
          </div>
          <div style={styles.impactCard}>
            <span style={{ ...styles.impactNum, color: '#2D7A52' }}>{formatCurrency(summary?.total_potential_savings)}</span>
            <span style={styles.impactLabel}>Monthly Savings Available</span>
          </div>
          <div style={styles.impactCard}>
            <span style={styles.impactNum}>{summary?.closed_won || 0}</span>
            <span style={styles.impactLabel}>Conversions to Date</span>
          </div>
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
    padding: '32px 40px',
    background: '#FAF7F1',
    minHeight: '100vh',
    fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
  },
  skeleton: { height: 500, borderRadius: 12, background: '#F2EDE2' },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 24,
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 28,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
  },
  subtitle: { fontSize: 13, color: '#8B8A7E', marginTop: 4 },
  staleInline: { color: '#B25F18', fontWeight: 600 },
  sourceStatus: { display: 'flex', gap: 12 },
  sourceItem: { display: 'flex', alignItems: 'center', gap: 6 },
  sourceDot: { width: 8, height: 8, borderRadius: '50%' },
  sourceLabel: { fontSize: 11, color: '#4F554E', fontWeight: 500 },
  rateGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: 12,
    marginBottom: 32,
  },
  rateCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 16,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  rateCardSelected: {
    borderColor: '#1F3D2E',
    boxShadow: '0 4px 12px rgba(31, 61, 46, 0.1)',
  },
  rateCardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  rateCardLabel: { fontSize: 12, fontWeight: 600, color: '#1A1F1B' },
  rateCardMargin: { fontSize: 9, color: '#8B8A7E', background: '#F6F2EA', padding: '2px 6px', borderRadius: 4 },
  rateCardBody: { display: 'flex', justifyContent: 'space-between', marginBottom: 12 },
  rateCardPerennia: { display: 'flex', flexDirection: 'column' },
  rateCardPLabel: { fontSize: 9, color: '#2D7A52', textTransform: 'uppercase', letterSpacing: '0.04em' },
  rateCardPValue: { fontSize: 22, fontWeight: 700, color: '#1F3D2E', fontFamily: "'Geist Mono', monospace" },
  rateCardMarket: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' },
  rateCardMLabel: { fontSize: 9, color: '#8B8A7E', textTransform: 'uppercase' },
  rateCardMValue: { fontSize: 14, color: '#4F554E', fontFamily: "'Geist Mono', monospace" },
  rateCardFooter: { display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #F2EDE2' },
  rateCardSource: { fontSize: 9, color: '#B5B2A4', textTransform: 'uppercase' },
  rateCardTime: { fontSize: 9, color: '#B5B2A4' },
  detailSection: { marginBottom: 32 },
  detailHeader: { marginBottom: 16 },
  detailTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 18,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
  },
  detailGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 16,
  },
  detailCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    padding: 20,
  },
  detailCardTitle: { fontSize: 12, fontWeight: 600, color: '#1A1F1B', margin: '0 0 16px', textTransform: 'uppercase', letterSpacing: '0.03em' },
  breakdownRow: { display: 'flex', justifyContent: 'space-between', padding: '8px 0' },
  breakdownLabel: { fontSize: 13, color: '#4F554E' },
  breakdownValue: { fontSize: 13, fontFamily: "'Geist Mono', monospace", color: '#1A1F1B' },
  breakdownDivider: { height: 1, background: '#ECE6D8', margin: '8px 0' },
  chartPlaceholder: {
    height: 120,
    background: '#FBF8F2',
    borderRadius: 8,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    overflow: 'hidden',
  },
  chartLine: {
    position: 'absolute',
    bottom: '40%',
    left: 0,
    right: 0,
    height: 2,
    background: 'linear-gradient(90deg, #ECE6D8, #2D7A52, #B8924A, #1F3D2E)',
    opacity: 0.4,
  },
  chartText: { fontSize: 11, color: '#B5B2A4', zIndex: 1 },
  marginConfig: {},
  marginRow: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #F2EDE2' },
  marginLabel: { fontSize: 13, color: '#4F554E' },
  marginValue: { fontSize: 14, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  marginNote: { fontSize: 11, color: '#8B8A7E', lineHeight: 1.5, marginTop: 12 },
  impactSection: { marginBottom: 32 },
  impactGrid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 16 },
  impactCard: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    padding: 20,
    textAlign: 'center',
  },
  impactNum: { display: 'block', fontSize: 28, fontWeight: 700, color: '#1A1F1B', fontFamily: "'Fraunces', serif" },
  impactLabel: { display: 'block', fontSize: 11, color: '#8B8A7E', marginTop: 4 },
};
