import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import './MorningBriefingCard.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getLocalDateString() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function healthLabel(level) {
  if (level === 'red') return 'Needs Attention';
  if (level === 'yellow') return 'Monitor';
  return 'On Track';
}

function formatVolume(v) {
  if (!v) return '$0';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function TrendArrow({ value, invertColor }) {
  if (value === undefined || value === null) return null;
  const num = Number(value);
  if (num === 0) return <span className="trend-arrow neutral">--</span>;
  const up = num > 0;
  const colorClass = invertColor ? (up ? 'down' : 'up') : (up ? 'up' : 'down');
  return (
    <span className={`trend-arrow ${colorClass}`}>
      {up ? '\u25B2' : '\u25BC'} {Math.abs(num)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Section sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ title, icon, count, isOpen, onToggle }) {
  return (
    <button className="briefing-section-header" onClick={onToggle} type="button">
      <span className="section-icon">{icon}</span>
      <span className="section-title">{title}</span>
      {count !== undefined && count > 0 && (
        <span className="section-badge">{count}</span>
      )}
      <span className="section-chevron">{isOpen ? '\u25BE' : '\u25B8'}</span>
    </button>
  );
}

function PipelineSection({ pipeline }) {
  if (!pipeline || pipeline.active_count === 0) return null;
  const byStage = pipeline.by_stage || {};
  const stageEntries = Object.entries(byStage).slice(0, 5);
  return (
    <div className="section-content">
      <div className="metric-row">
        <div className="metric-item">
          <span className="metric-value">{pipeline.active_count}</span>
          <span className="metric-label">Active Loans</span>
        </div>
        <div className="metric-item">
          <span className="metric-value">{formatVolume(pipeline.total_volume)}</span>
          <span className="metric-label">Pipeline Volume</span>
        </div>
        <div className="metric-item">
          <span className="metric-value">{pipeline.closing_soon || 0}</span>
          <span className="metric-label">Closing Soon</span>
        </div>
      </div>
      {stageEntries.length > 0 && (
        <div className="stage-pills">
          {stageEntries.map(([stage, count]) => (
            <span className="stage-pill" key={stage}>
              {stage.replace(/_/g, ' ')} <strong>{count}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AtRiskSection({ items }) {
  if (!items || items.length === 0) return <p className="section-empty">No at-risk loans</p>;
  return (
    <div className="section-content">
      <ul className="briefing-list at-risk-list">
        {items.slice(0, 5).map((loan, i) => (
          <li key={loan.loan_id || i}>
            <a href={`/loans/${loan.loan_id}`} className="item-link">
              <strong>{loan.borrower}</strong>
            </a>
            <span className="item-detail">{loan.reason}</span>
            {loan.days_in_stage && (
              <span className="item-badge warn">{Math.round(loan.days_in_stage)}d</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConditionsSection({ conditions }) {
  if (!conditions || conditions.length === 0) return <p className="section-empty">No open conditions</p>;
  const pastDueCount = conditions.filter(c => c.past_due).length;
  return (
    <div className="section-content">
      {pastDueCount > 0 && (
        <div className="past-due-banner">{pastDueCount} past due</div>
      )}
      <ul className="briefing-list conditions-list">
        {conditions.slice(0, 5).map((c, i) => (
          <li key={i} className={c.past_due ? 'past-due' : ''}>
            <span className={`severity-dot ${c.severity || 'medium'}`} />
            <span className="item-text">{c.title}</span>
            {c.loan_number && <span className="item-loan">#{c.loan_number}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StaleLeadsSection({ leads }) {
  if (!leads || leads.length === 0) return <p className="section-empty">No stale leads</p>;
  return (
    <div className="section-content">
      <ul className="briefing-list leads-list">
        {leads.slice(0, 5).map((lead, i) => (
          <li key={lead.lead_id || i}>
            <a href={`/leads/${lead.lead_id}`} className="item-link">
              <strong>{lead.name}</strong>
            </a>
            {lead.score && <span className="item-badge score">Score {lead.score}</span>}
            <span className="item-detail">{Math.round(lead.days_silent || 0)} days silent</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AppointmentsSection({ appointments }) {
  if (!appointments || appointments.length === 0) return <p className="section-empty">No appointments today</p>;
  return (
    <div className="section-content">
      <ul className="briefing-list appointments-list">
        {appointments.map((appt, i) => (
          <li key={appt.id || i}>
            <span className="appt-time">{appt.time}</span>
            <span className="item-text">{appt.attendee}</span>
            <span className="item-detail">{appt.type}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function YesterdaySection({ yesterday }) {
  if (!yesterday) return null;
  const { funded, new_loans, conversions } = yesterday;
  if (!funded && !new_loans && !conversions) return <p className="section-empty">No activity yesterday</p>;
  return (
    <div className="section-content">
      <div className="metric-row">
        {funded > 0 && (
          <div className="metric-item">
            <span className="metric-value">{funded}</span>
            <span className="metric-label">Funded</span>
          </div>
        )}
        {new_loans > 0 && (
          <div className="metric-item">
            <span className="metric-value">{new_loans}</span>
            <span className="metric-label">New Loans</span>
          </div>
        )}
        {conversions > 0 && (
          <div className="metric-item">
            <span className="metric-value">{conversions}</span>
            <span className="metric-label">Conversions</span>
          </div>
        )}
      </div>
    </div>
  );
}

function TeamSection({ team, level }) {
  if (!team) return null;

  if (level === 'manager' && team.members) {
    return (
      <div className="section-content">
        <table className="briefing-table">
          <thead>
            <tr><th>Name</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
          </thead>
          <tbody>
            {team.members.map((m, i) => (
              <tr key={i}>
                <td><span className={`health-dot ${m.health}`} /> {m.name}</td>
                <td>{m.loan_count}</td>
                <td>{formatVolume(m.volume)}</td>
                <td>{m.health}{m.at_risk_count > 0 ? ` \u00B7 ${m.at_risk_count} at-risk` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {team.attention_items && team.attention_items.length > 0 && (
          <div className="attention-items">
            <h5>Attention Needed</h5>
            <ul>
              {team.attention_items.map((item, i) => (
                <li key={i}><strong>{item.user_name}</strong> -- {item.issue}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (level === 'leadership' && team.branches) {
    return (
      <div className="section-content">
        {team.org_snapshot && (
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{team.org_snapshot.active_count}</span>
              <span className="metric-label">Active Loans</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(team.org_snapshot.total_volume)}</span>
              <span className="metric-label">Pipeline</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team.org_snapshot.funded_this_week}</span>
              <span className="metric-label">Funded This Week</span>
            </div>
          </div>
        )}
        <table className="briefing-table">
          <thead>
            <tr><th>Branch</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
          </thead>
          <tbody>
            {team.branches.map((b, i) => (
              <tr key={i}>
                <td><span className={`health-dot ${b.health}`} /> {b.name}</td>
                <td>{b.loan_count}</td>
                <td>{formatVolume(b.volume)}</td>
                <td>{b.health}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MorningBriefingCard() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem('briefing_collapsed') === 'true';
  });
  const [dismissed, setDismissed] = useState(() => {
    const d = localStorage.getItem('briefing_dismissed_date');
    return d === getLocalDateString();
  });
  const [narrativeExpanded, setNarrativeExpanded] = useState(false);
  const [openSections, setOpenSections] = useState({
    pipeline: true,
    at_risk: true,
    conditions: true,
    stale_leads: false,
    appointments: true,
    yesterday: false,
    team: false,
  });

  // ----- Fetch today's briefing -----
  const fetchBriefing = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/today', {
        validateStatus: (status) => status === 200 || status === 204,
      });
      if (res.status === 204) {
        // No briefing yet today
        setBriefing(null);
      } else if (res.data && res.data.status === 'delivered') {
        setBriefing(res.data);
        // Mark as viewed
        if (!res.data.viewed_in_app) {
          api.post(`/api/v1/briefing/${res.data.id}/viewed`).catch(() => {});
        }
      }
    } catch (_err) {
      // Silent -- briefings are supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!dismissed) fetchBriefing();
    else setLoading(false);
  }, [dismissed, fetchBriefing]);

  // ----- Actions -----
  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('briefing_collapsed', String(next));
  };

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem('briefing_dismissed_date', getLocalDateString());
  };

  const toggleSection = (key) => {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleRefresh = async (e) => {
    e.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/v1/briefing/generate-now?force=true');
      toast.success('Briefing refresh started -- it may take a moment.');
      // Poll briefly for the new briefing (generation is async via Celery)
      setTimeout(async () => {
        await fetchBriefing();
        setRefreshing(false);
      }, 4000);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail || 'Could not refresh briefing');
      setRefreshing(false);
    }
  };

  // ----- Compute health indicator -----
  const computeHealth = () => {
    if (!briefing) return 'green';
    const atRiskCount = (briefing.at_risk || []).length;
    const staleCount = (briefing.stale_leads || []).length;
    const pastDueConditions = (briefing.conditions || []).filter(c => c.past_due).length;
    if (pastDueConditions >= 2 || atRiskCount >= 3) return 'red';
    if (atRiskCount >= 1 || staleCount >= 3 || pastDueConditions >= 1) return 'yellow';
    return 'green';
  };

  // ----- Render guards -----
  if (loading || dismissed) return null;
  if (!briefing) return null;

  const {
    ai_narrative,
    pipeline,
    at_risk,
    stale_leads,
    appointments,
    conditions,
    yesterday,
    team,
    briefing_level,
    briefing_date,
  } = briefing;

  const health = computeHealth();
  const narrativeText = ai_narrative || '';
  const showNarrativeTruncated = narrativeText.length > 200 && !narrativeExpanded;

  return (
    <div className={`morning-briefing-card health-${health}`}>
      {/* --- Header --- */}
      <div className="briefing-header" onClick={toggleCollapse}>
        <div className="briefing-title">
          <span className={`health-indicator ${health}`} title={healthLabel(health)} />
          <h3>Morning Briefing</h3>
          <span className="health-label">{healthLabel(health)}</span>
          <span className="briefing-date">{briefing_date}</span>
        </div>
        <div className="briefing-actions">
          <button
            className="briefing-refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh briefing"
          >
            <span className={refreshing ? 'spin' : ''}>&#x21bb;</span>
          </button>
          <button className="briefing-collapse-btn" title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '\u25B8' : '\u25BE'}
          </button>
          <button
            className="briefing-dismiss-btn"
            onClick={(e) => { e.stopPropagation(); dismiss(); }}
            title="Dismiss for today"
          >
            &#x2715;
          </button>
        </div>
      </div>

      {/* --- Body --- */}
      {!collapsed && (
        <div className="briefing-body">
          {/* AI Narrative */}
          {narrativeText && (
            <div className="briefing-narrative">
              <div className={`narrative-text ${showNarrativeTruncated ? 'truncated' : ''}`}>
                {showNarrativeTruncated ? narrativeText.slice(0, 200) + '...' : narrativeText}
              </div>
              {narrativeText.length > 200 && (
                <button
                  className="narrative-toggle"
                  onClick={() => setNarrativeExpanded(!narrativeExpanded)}
                >
                  {narrativeExpanded ? 'Show less' : 'Read more'}
                </button>
              )}
            </div>
          )}

          {/* Pipeline Health */}
          {pipeline && pipeline.active_count > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Pipeline Health"
                icon="&#x1F4CA;"
                count={pipeline.active_count}
                isOpen={openSections.pipeline}
                onToggle={() => toggleSection('pipeline')}
              />
              {openSections.pipeline && <PipelineSection pipeline={pipeline} />}
            </div>
          )}

          {/* SLA Alerts / At-Risk */}
          {at_risk && at_risk.length > 0 && (
            <div className="briefing-section section-warn">
              <SectionHeader
                title="SLA Alerts"
                icon="&#x26A0;"
                count={at_risk.length}
                isOpen={openSections.at_risk}
                onToggle={() => toggleSection('at_risk')}
              />
              {openSections.at_risk && <AtRiskSection items={at_risk} />}
            </div>
          )}

          {/* Conditions */}
          {conditions && conditions.length > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Open Conditions"
                icon="&#x1F4CB;"
                count={conditions.length}
                isOpen={openSections.conditions}
                onToggle={() => toggleSection('conditions')}
              />
              {openSections.conditions && <ConditionsSection conditions={conditions} />}
            </div>
          )}

          {/* Stale Leads */}
          {stale_leads && stale_leads.length > 0 && (
            <div className="briefing-section section-caution">
              <SectionHeader
                title="Lead Activity"
                icon="&#x1F525;"
                count={stale_leads.length}
                isOpen={openSections.stale_leads}
                onToggle={() => toggleSection('stale_leads')}
              />
              {openSections.stale_leads && <StaleLeadsSection leads={stale_leads} />}
            </div>
          )}

          {/* Appointments */}
          {appointments && appointments.length > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Today's Schedule"
                icon="&#x1F4C5;"
                count={appointments.length}
                isOpen={openSections.appointments}
                onToggle={() => toggleSection('appointments')}
              />
              {openSections.appointments && <AppointmentsSection appointments={appointments} />}
            </div>
          )}

          {/* Yesterday Recap */}
          {yesterday && (yesterday.funded > 0 || yesterday.new_loans > 0 || yesterday.conversions > 0) && (
            <div className="briefing-section">
              <SectionHeader
                title="Yesterday Recap"
                icon="&#x1F4C8;"
                isOpen={openSections.yesterday}
                onToggle={() => toggleSection('yesterday')}
              />
              {openSections.yesterday && <YesterdaySection yesterday={yesterday} />}
            </div>
          )}

          {/* Team (Manager) / Org (Leadership) */}
          {team && (briefing_level === 'manager' || briefing_level === 'leadership') && (
            <div className="briefing-section section-team">
              <SectionHeader
                title={briefing_level === 'leadership' ? 'Organization Overview' : 'Your Team'}
                icon="&#x1F465;"
                isOpen={openSections.team}
                onToggle={() => toggleSection('team')}
              />
              {openSections.team && <TeamSection team={team} level={briefing_level} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
