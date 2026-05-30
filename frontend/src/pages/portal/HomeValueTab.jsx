/**
 * HomeValueTab — borrower-facing Home Value / equity tab for the MUM portal.
 *
 * Renders the `home_value` payload from the PURL-authed borrower dashboard
 * (GET /api/v1/portal/borrower/{crmLoanId}/dashboard ->
 *  { has_baseline, baseline, current_valuation, equity, insights,
 *    valuation_history, chart_data }), and degrades gracefully to the locally
 * computed MUM estimate when the backend payload is absent or has no baseline.
 *
 * Self-contained: inline styles only, no dependency on the (deleted) portal CSS.
 *
 * Props:
 *   homeValue       backend home_value object (may be null/undefined)
 *   fallbackValue   locally-estimated property value (MUMPortal computes this)
 *   fallbackBalance locally-known current loan balance
 *   purchasePrice   original purchase price (for "what you paid -> now")
 */
import React from 'react';

const fmt = (amount, decimals = 0) => {
  if (amount == null || Number.isNaN(Number(amount))) return '$0';
  return Number(amount).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

const pct = (n, decimals = 1) => {
  if (n == null || Number.isNaN(Number(n))) return '0%';
  return `${Number(n).toFixed(decimals)}%`;
};

const card = {
  background: '#fff',
  borderRadius: 12,
  padding: 24,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  marginBottom: 16,
};
const heroLabel = { fontSize: 12, fontWeight: 700, letterSpacing: 0.6, color: '#64748b' };
const heroAmount = { fontSize: 36, fontWeight: 700, color: '#0f766e', margin: '4px 0 2px' };
const heroSub = { fontSize: 13, color: '#94a3b8' };
const estimatedTag = {
  display: 'inline-block',
  fontSize: 11,
  fontWeight: 700,
  color: '#475569',
  background: '#f1f5f9',
  borderRadius: 999,
  padding: '2px 10px',
  marginBottom: 8,
};
const statsGrid = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
  gap: 16,
};
const statCell = { padding: '12px 0' };
const statLabel = { fontSize: 11, fontWeight: 700, letterSpacing: 0.4, color: '#94a3b8', display: 'block' };
const statValue = { fontSize: 18, fontWeight: 600, color: '#1a202c', display: 'block', marginTop: 4 };
const statValuePositive = { ...statValue, color: '#0f766e' };
const sectionTitle = { margin: '0 0 12px', fontSize: 15, fontWeight: 600, color: '#1a202c' };
const insightRow = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  padding: '10px 0',
  borderTop: '1px solid #f1f5f9',
  fontSize: 14,
  color: '#334155',
};
const emptyState = { textAlign: 'center', padding: '32px 16px', color: '#64748b' };

// Low — estimate — high range track.
const RangeBar = ({ low, estimate, high }) => {
  if (low == null || high == null || high <= low) return null;
  const clampedEstimate = Math.min(Math.max(estimate ?? (low + high) / 2, low), high);
  const pos = ((clampedEstimate - low) / (high - low)) * 100;
  return (
    <div style={{ marginTop: 4 }}>
      <div
        style={{
          position: 'relative',
          height: 8,
          borderRadius: 999,
          background: 'linear-gradient(90deg,#a7f3d0,#5eead4,#2dd4bf)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: -4,
            left: `${pos}%`,
            transform: 'translateX(-50%)',
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: '#0f766e',
            border: '2px solid #fff',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 12, color: '#64748b' }}>
        <span>{fmt(low)}</span>
        <span style={{ fontWeight: 600, color: '#0f766e' }}>{fmt(clampedEstimate)}</span>
        <span>{fmt(high)}</span>
      </div>
    </div>
  );
};

// Two-color stacked bar: equity vs remaining balance.
const EquityBar = ({ value, balance }) => {
  if (!value || value <= 0) return null;
  const safeBalance = Math.max(0, Math.min(balance ?? 0, value));
  const equity = Math.max(0, value - safeBalance);
  const equityPct = (equity / value) * 100;
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', height: 28, borderRadius: 8, overflow: 'hidden', background: '#e2e8f0' }}>
        <div
          style={{ width: `${equityPct}%`, background: '#0f766e' }}
          title={`Your equity: ${fmt(equity)}`}
        />
        <div
          style={{ width: `${100 - equityPct}%`, background: '#cbd5e1' }}
          title={`Remaining balance: ${fmt(safeBalance)}`}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 13 }}>
        <span style={{ color: '#0f766e', fontWeight: 600 }}>
          Equity {fmt(equity)} ({pct(equityPct, 0)})
        </span>
        <span style={{ color: '#64748b' }}>Balance {fmt(safeBalance)}</span>
      </div>
    </div>
  );
};

export default function HomeValueTab({
  homeValue,
  fallbackValue = 0,
  fallbackBalance = 0,
  purchasePrice = 0,
}) {
  const hasBaseline = !!homeValue?.has_baseline;

  // Prefer backend valuation; fall back to the locally computed MUM estimate.
  const currentValuation = homeValue?.current_valuation || {};
  const equityData = homeValue?.equity || {};
  const baseline = homeValue?.baseline || {};

  const estimatedValue =
    currentValuation.estimated_value ??
    currentValuation.value ??
    fallbackValue;
  const valueLow = currentValuation.value_low ?? currentValuation.low;
  const valueHigh = currentValuation.value_high ?? currentValuation.high;

  const currentBalance =
    equityData.current_balance ??
    equityData.balance ??
    fallbackBalance;

  const equity =
    equityData.equity ??
    (estimatedValue != null && currentBalance != null
      ? estimatedValue - currentBalance
      : null);

  const ltv =
    equityData.ltv ??
    (estimatedValue ? (currentBalance / estimatedValue) * 100 : null);

  const ownershipPct = ltv != null ? Math.max(0, Math.min(100, 100 - ltv)) : null;

  const purchase = baseline.purchase_price ?? purchasePrice;
  const appreciationAmount =
    homeValue?.appreciation_amount ??
    (purchase && estimatedValue ? estimatedValue - purchase : null);
  const appreciationPct =
    homeValue?.appreciation_pct ??
    (purchase ? ((estimatedValue - purchase) / purchase) * 100 : null);

  const insights = Array.isArray(homeValue?.insights) ? homeValue.insights : [];

  return (
    <div>
      {/* Hero value block */}
      <div style={card}>
        <span style={estimatedTag}>ESTIMATED</span>
        <div>
          <span style={heroLabel}>YOUR HOME IS WORTH ABOUT</span>
          <div style={heroAmount}>{fmt(estimatedValue)}</div>
          <span style={heroSub}>
            {hasBaseline
              ? 'Based on recent market data for your area'
              : 'Estimated from your purchase price and typical local appreciation'}
          </span>
        </div>
        <RangeBar low={valueLow} estimate={estimatedValue} high={valueHigh} />
      </div>

      {/* Stat grid */}
      <div style={card}>
        <div style={statsGrid}>
          <div style={statCell}>
            <span style={statLabel}>WHAT YOU PAID</span>
            <span style={statValue}>{fmt(purchase)}</span>
          </div>
          <div style={statCell}>
            <span style={statLabel}>CHANGE SINCE PURCHASE</span>
            <span style={appreciationAmount >= 0 ? statValuePositive : statValue}>
              {appreciationAmount != null
                ? `${appreciationAmount >= 0 ? '+' : ''}${fmt(appreciationAmount)}`
                : '—'}
              {appreciationPct != null && (
                <span style={{ fontSize: 13, fontWeight: 500, color: '#94a3b8', marginLeft: 6 }}>
                  ({appreciationPct >= 0 ? '+' : ''}{pct(appreciationPct)})
                </span>
              )}
            </span>
          </div>
          <div style={statCell}>
            <span style={statLabel}>CURRENT BALANCE</span>
            <span style={statValue}>{fmt(currentBalance)}</span>
          </div>
          <div style={statCell}>
            <span style={statLabel}>YOUR EQUITY</span>
            <span style={statValuePositive}>{equity != null ? fmt(equity) : '—'}</span>
          </div>
          <div style={statCell}>
            <span style={statLabel}>OWNERSHIP</span>
            <span style={statValue}>
              {ownershipPct != null ? `You own ${pct(ownershipPct, 0)} of your home` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Equity breakdown bar */}
      <div style={card}>
        <h3 style={sectionTitle}>How much of your home you own</h3>
        <EquityBar value={estimatedValue} balance={currentBalance} />
      </div>

      {/* Insights */}
      {insights.length > 0 ? (
        <div style={card}>
          <h3 style={sectionTitle}>What this means for you</h3>
          <div>
            {insights.map((insight, idx) => {
              const text = typeof insight === 'string'
                ? insight
                : (insight?.borrower_text || insight?.text || insight?.message || insight?.title || '');
              if (!text) return null;
              return (
                <div key={insight?.id != null ? insight.id : idx} style={insightRow}>
                  <span style={{ color: '#0f766e', fontWeight: 700, lineHeight: '20px' }}>•</span>
                  <span>{text}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : !hasBaseline ? (
        <div style={card}>
          <div style={emptyState}>
            <h3 style={{ margin: '0 0 6px', fontSize: 16, color: '#334155' }}>
              Tracking your home value
            </h3>
            <p style={{ margin: 0, fontSize: 14 }}>
              We&rsquo;ll keep an eye on your home&rsquo;s estimated value and equity over
              time. Check back here to see how your investment grows.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
