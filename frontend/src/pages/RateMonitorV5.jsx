/**
 * Rate Monitor V5 — "Aria Copilot"
 *
 * Conversational AI-first layout. Large central card showing what Aria
 * is doing right now. Rates are contextual. The primary CTA is always
 * "Let Aria handle it" with transparency into her decision-making.
 * Optimized for: LOs who trust AI and want minimal manual intervention.
 */
import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/rate-watch';
const PRODUCTS = {
  '30_fixed': '30 Yr Fixed', '15_fixed': '15 Yr Fixed', '30_jumbo': '30 Yr Jumbo',
  '7_6_sofr_arm': '7/6 ARM', '30_fha': '30 Yr FHA', '30_va': '30 Yr VA',
};

export default function RateMonitorV5() {
  const [rates, setRates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ratesRes, summaryRes, oppsRes] = await Promise.all([
        fetch(`${API_BASE}/current-rates`, { credentials: 'include' }),
        fetch(`${API_BASE}/portfolio-summary`, { credentials: 'include' }),
        fetch(`${API_BASE}/opportunities?limit=30`, { credentials: 'include' }),
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

  const pendingCount = opportunities.filter(o => o.status === 'detected').length;
  const inProgress = opportunities.filter(o => ['outreach_sent', 'borrower_responded', 'meeting_booked'].includes(o.status));

  return (
    <div style={styles.page}>
      {/* Aria Status Card */}
      <div style={styles.ariaCard}>
        <div style={styles.ariaHeader}>
          <div style={styles.ariaAvatar}>
            <span style={styles.ariaAvatarText}>A</span>
          </div>
          <div style={styles.ariaInfo}>
            <h1 style={styles.ariaName}>Aria Rate Monitor</h1>
            <span style={styles.ariaStatus}>
              <span style={styles.ariaDot} />
              Monitoring {summary?.active_targets || 0} loan targets
            </span>
          </div>
        </div>

        <div style={styles.ariaBody}>
          {pendingCount > 0 ? (
            <>
              <p style={styles.ariaMessage}>
                I've found <strong>{pendingCount} refi {pendingCount === 1 ? 'opportunity' : 'opportunities'}</strong> where
                your borrowers can save money. Total potential: <strong>{formatCurrency(summary?.total_potential_savings)}/month</strong>.
              </p>
              <div style={styles.ariaActions}>
                <button style={styles.ariaPrimaryBtn}>Let Me Handle All {pendingCount}</button>
                <button style={styles.ariaSecondaryBtn}>Review Each One</button>
              </div>
            </>
          ) : (
            <p style={styles.ariaMessage}>
              All clear. I'm watching the market and will alert you the moment any of your
              borrowers' target rates are hit. Current rates are{' '}
              {rates?.stale ? <span style={styles.ariaWarn}>stale (over 24h old)</span> : 'fresh'}.
            </p>
          )}
        </div>

        {/* Today's Rates */}
        <div style={styles.ariaRates}>
          {rates?.rates?.slice(0, 4).map(r => (
            <div key={r.product} style={styles.ariaRateItem}>
              <span style={styles.ariaRateLabel}>{PRODUCTS[r.product]}</span>
              <span style={styles.ariaRateValue}>{formatRate(r.perennia_rate)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Two Columns: Pipeline + Activity */}
      <div style={styles.columns}>
        {/* Pipeline */}
        <div style={styles.panel}>
          <h2 style={styles.panelTitle}>Active Pipeline</h2>
          <div style={styles.pipelineStages}>
            <PipelineStage
              label="Detected"
              count={opportunities.filter(o => o.status === 'detected').length}
              color="#B8924A"
            />
            <PipelineStage
              label="Outreach Sent"
              count={opportunities.filter(o => o.status === 'outreach_sent').length}
              color="#1F3D2E"
            />
            <PipelineStage
              label="Responded"
              count={opportunities.filter(o => o.status === 'borrower_responded').length}
              color="#2D7A52"
            />
            <PipelineStage
              label="Meeting Booked"
              count={opportunities.filter(o => o.status === 'meeting_booked').length}
              color="#2D7A52"
            />
            <PipelineStage
              label="Closed Won"
              count={opportunities.filter(o => o.status === 'closed_won').length}
              color="#1F3D2E"
              success
            />
          </div>
        </div>

        {/* Aria's Activity */}
        <div style={styles.panel}>
          <h2 style={styles.panelTitle}>Aria's Recent Actions</h2>
          <div style={styles.activityList}>
            {inProgress.length === 0 && pendingCount === 0 ? (
              <p style={styles.activityEmpty}>No recent activity. Aria will log her actions here as she works opportunities.</p>
            ) : (
              [...inProgress, ...opportunities.filter(o => o.status === 'detected')].slice(0, 8).map(opp => (
                <div key={opp.id} style={styles.activityItem}>
                  <div style={styles.activityDot} />
                  <div style={styles.activityContent}>
                    <span style={styles.activityText}>
                      {opp.status === 'detected' && `Detected ${formatCurrency(opp.monthly_savings)}/mo savings for Loan #${opp.loan_id}`}
                      {opp.status === 'outreach_sent' && `Sent personalized outreach for Loan #${opp.loan_id}`}
                      {opp.status === 'borrower_responded' && `Borrower responded for Loan #${opp.loan_id}`}
                      {opp.status === 'meeting_booked' && `Meeting booked for Loan #${opp.loan_id}`}
                    </span>
                    <span style={styles.activityTime}>
                      {opp.detected_at && new Date(opp.detected_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Pending Approvals */}
      {pendingCount > 0 && (
        <div style={styles.pendingSection}>
          <h2 style={styles.panelTitle}>Pending Your Review</h2>
          <div style={styles.pendingGrid}>
            {opportunities.filter(o => o.status === 'detected').map(opp => (
              <div key={opp.id} style={styles.pendingCard}>
                <div style={styles.pendingTop}>
                  <span style={styles.pendingLoan}>Loan #{opp.loan_id}</span>
                  <span style={styles.pendingSavings}>{formatCurrency(opp.monthly_savings)}/mo</span>
                </div>
                <div style={styles.pendingRates}>
                  {formatRate(opp.current_rate)} → {formatRate(opp.perennia_rate)}
                </div>
                <div style={styles.pendingActions}>
                  <button style={styles.pendingApprove}>Approve Outreach</button>
                  <button style={styles.pendingSkip}>Skip</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PipelineStage({ label, count, color, success }) {
  return (
    <div style={styles.stageItem}>
      <div style={{
        ...styles.stageBar,
        background: count > 0 ? color : '#F2EDE2',
        opacity: count > 0 ? 1 : 0.5,
      }}>
        <span style={styles.stageCount}>{count}</span>
      </div>
      <span style={styles.stageLabel}>{label}</span>
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
  skeleton: { height: 400, borderRadius: 14, background: '#F2EDE2' },
  ariaCard: {
    background: 'linear-gradient(160deg, #E5EDE6 0%, #FFFFFF 40%, #FBF8F2 100%)',
    border: '1px solid #D8E8DC',
    borderRadius: 16,
    padding: 32,
    marginBottom: 24,
  },
  ariaHeader: { display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 },
  ariaAvatar: {
    width: 48,
    height: 48,
    borderRadius: 12,
    background: '#1F3D2E',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  ariaAvatarText: { color: '#F5F2E9', fontSize: 20, fontWeight: 700, fontFamily: "'Fraunces', serif" },
  ariaInfo: {},
  ariaName: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 22,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: 0,
  },
  ariaStatus: { fontSize: 12, color: '#4F554E', display: 'flex', alignItems: 'center', gap: 6 },
  ariaDot: { width: 6, height: 6, borderRadius: '50%', background: '#2D7A52' },
  ariaBody: { marginBottom: 24 },
  ariaMessage: { fontSize: 15, color: '#1A1F1B', lineHeight: 1.6, margin: '0 0 16px' },
  ariaWarn: { color: '#B25F18', fontWeight: 600 },
  ariaActions: { display: 'flex', gap: 12 },
  ariaPrimaryBtn: {
    padding: '12px 24px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
  ariaSecondaryBtn: {
    padding: '12px 24px',
    background: 'transparent',
    color: '#1F3D2E',
    border: '1px solid #1F3D2E',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
  },
  ariaRates: {
    display: 'flex',
    gap: 24,
    paddingTop: 20,
    borderTop: '1px solid #D8E8DC',
  },
  ariaRateItem: { display: 'flex', flexDirection: 'column' },
  ariaRateLabel: { fontSize: 10, color: '#8B8A7E', textTransform: 'uppercase', letterSpacing: '0.04em' },
  ariaRateValue: { fontSize: 18, fontWeight: 600, color: '#1A1F1B', fontFamily: "'Geist Mono', monospace" },
  columns: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 24,
    marginBottom: 24,
  },
  panel: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 24,
  },
  panelTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: 16,
    fontWeight: 600,
    color: '#1A1F1B',
    margin: '0 0 16px',
  },
  pipelineStages: { display: 'flex', gap: 8 },
  stageItem: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 },
  stageBar: {
    width: '100%',
    height: 48,
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stageCount: { fontSize: 18, fontWeight: 700, color: '#FFFFFF', fontFamily: "'Fraunces', serif" },
  stageLabel: { fontSize: 10, color: '#8B8A7E', textAlign: 'center' },
  activityList: {},
  activityEmpty: { fontSize: 13, color: '#8B8A7E' },
  activityItem: { display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid #F2EDE2' },
  activityDot: { width: 8, height: 8, borderRadius: '50%', background: '#2D7A52', marginTop: 5, flexShrink: 0 },
  activityContent: { display: 'flex', flexDirection: 'column', flex: 1 },
  activityText: { fontSize: 13, color: '#1A1F1B' },
  activityTime: { fontSize: 11, color: '#8B8A7E', marginTop: 2 },
  pendingSection: {
    background: '#FFFFFF',
    border: '1px solid #ECE6D8',
    borderRadius: 12,
    padding: 24,
  },
  pendingGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: 12,
  },
  pendingCard: {
    border: '1px solid #ECE6D8',
    borderRadius: 10,
    padding: 16,
  },
  pendingTop: { display: 'flex', justifyContent: 'space-between', marginBottom: 8 },
  pendingLoan: { fontSize: 13, fontWeight: 600, color: '#1A1F1B' },
  pendingSavings: { fontSize: 13, fontWeight: 600, color: '#B8924A' },
  pendingRates: { fontSize: 12, color: '#4F554E', fontFamily: "'Geist Mono', monospace", marginBottom: 12 },
  pendingActions: { display: 'flex', gap: 8 },
  pendingApprove: {
    flex: 1,
    padding: '7px 12px',
    background: '#1F3D2E',
    color: '#F5F2E9',
    border: 'none',
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
  },
  pendingSkip: {
    padding: '7px 12px',
    background: 'transparent',
    color: '#8B8A7E',
    border: '1px solid #ECE6D8',
    borderRadius: 6,
    fontSize: 11,
    cursor: 'pointer',
  },
};
